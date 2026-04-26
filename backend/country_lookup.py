"""Coordinate → country → regulations: a two-step live lookup.

Replaces the old bbox-against-3-cached-regions logic. Two pieces:

  1. resolve_country(lat, lon)
       Step 1: which country claims this point?
       - Primary: OSM Nominatim reverse-geocode. Works for anywhere within
         a sovereign EEZ that Nominatim has admin polygons for (i.e., the
         coastal/inland envelope, including most territorial seas).
       - Fallback: Marine Regions WFS EEZ layer for true offshore points
         outside Nominatim's admin polygons.
       - Returns None on the high seas (no sovereign).

  2. fetch_country_regulations(iso3)
       Step 2: pull the regulatory dossier for that country.
       - If we have a curated cache entry (ECU / PHL / EU today), return it
         as the primary block with confidence="curated".
       - Always include a FAOLEX search URL for the country/Fisheries scope
         as a citation-grade reference. FAOLEX itself is JS-rendered, so we
         do NOT pretend to have parsed individual records over plain HTTP —
         we cite the URL and (if seeded) the indexed record IDs from the
         finetune cache on disk.

Why both steps are exposed individually as agent tools: the LLM can reason
about partial answers ("country resolved but regs cache miss → still
report sovereign + search URL") without forcing one mega-call.

Every dict returned carries a `provenance` block:
  database, source_url, last_checked (ISO8601 UTC), confidence
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests

from regional_lookup import get_region_by_country

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
MARINE_REGIONS_WFS = "https://geo.vliz.be/geoserver/MarineRegions/wfs"
FAOLEX_SEARCH_URL = "https://www.fao.org/faolex/results/en/"
USER_AGENT = "overfished-iuu-pipeline/0.1 (research; contact via repo)"

# Resolves to backend/../finetune/data — the existing FAOLEX cache the
# finetune fetcher writes to. We read it in step 2 so any seeded country
# automatically gets richer evidence without backend code changes.
FINETUNE_DATA = (Path(__file__).resolve().parent.parent / "finetune" / "data")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Step 1: country resolution ────────────────────────────────────────────


# ISO2 → ISO3 for the maritime nations we care about. Kept short on purpose —
# anything not in this map falls back to using the ISO2 verbatim with a flag
# so the caller knows the conversion was best-effort.
_ISO2_TO_ISO3 = {
    "ar": "ARG", "au": "AUS", "be": "BEL", "br": "BRA", "ca": "CAN",
    "cl": "CHL", "cn": "CHN", "co": "COL", "cu": "CUB", "de": "DEU",
    "dk": "DNK", "ec": "ECU", "es": "ESP", "fj": "FJI", "fr": "FRA",
    "gb": "GBR", "gh": "GHA", "gr": "GRC", "hr": "HRV", "id": "IDN",
    "ie": "IRL", "in": "IND", "is": "ISL", "it": "ITA", "jp": "JPN",
    "ke": "KEN", "kr": "KOR", "lk": "LKA", "ma": "MAR", "mg": "MDG",
    "mx": "MEX", "my": "MYS", "mz": "MOZ", "na": "NAM", "ng": "NGA",
    "nl": "NLD", "no": "NOR", "nz": "NZL", "om": "OMN", "pa": "PAN",
    "pe": "PER", "pg": "PNG", "ph": "PHL", "pl": "POL", "pt": "PRT",
    "ru": "RUS", "sa": "SAU", "se": "SWE", "sn": "SEN", "th": "THA",
    "tn": "TUN", "tr": "TUR", "tw": "TWN", "tz": "TZA", "uk": "GBR",
    "us": "USA", "uy": "URY", "vn": "VNM", "za": "ZAF",
}


def _iso2_to_iso3(iso2: str | None) -> str | None:
    if not iso2:
        return None
    return _ISO2_TO_ISO3.get(iso2.lower())


def _resolve_via_nominatim(lat: float, lon: float) -> dict[str, Any] | None:
    try:
        r = requests.get(
            NOMINATIM_URL,
            params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 3},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError):
        return None
    addr = data.get("address") or {}
    iso2 = addr.get("country_code")
    if not iso2:
        return None
    iso3 = _iso2_to_iso3(iso2)
    return {
        "iso2": iso2.upper(),
        "iso3": iso3,
        "name": addr.get("country") or data.get("display_name"),
        "source": "nominatim",
        "source_url": (
            f"{NOMINATIM_URL}?lat={lat}&lon={lon}&format=jsonv2&zoom=3"
        ),
        "confidence": "live",
    }


def _resolve_via_marine_regions(lat: float, lon: float) -> dict[str, Any] | None:
    """Fallback for offshore points Nominatim can't place.

    Tries the 200-NM EEZ, then the IHO-merged EEZ layer. Returns the
    sovereign's ISO3 code if the EEZ feature carries it.

    Axis order: GeoServer WFS 2.0 with EPSG:4326 uses lat/lon (per the EPSG
    canonical axis order), NOT the lon/lat convention WKT/GeoJSON ship by
    default. Reversing this silently returned 0 features for valid points.
    """
    cql = f"INTERSECTS(the_geom,POINT({lat} {lon}))"
    for layer in ("MarineRegions:eez", "MarineRegions:eez_iho"):
        try:
            r = requests.get(
                MARINE_REGIONS_WFS,
                params={
                    "service": "WFS", "version": "2.0.0", "request": "GetFeature",
                    "typeNames": layer, "outputFormat": "application/json",
                    "srsName": "EPSG:4326", "count": "1", "CQL_FILTER": cql,
                },
                timeout=20,
            )
            r.raise_for_status()
            j = r.json()
        except (requests.RequestException, ValueError):
            continue
        feats = j.get("features") or []
        if not feats:
            continue
        # MR property keys are lowercase: iso_sov1 / sovereign1 / geoname.
        # Lower-case the dict so we don't have to know which casing the
        # particular layer/version emits.
        props = {k.lower(): v for k, v in (feats[0].get("properties") or {}).items()}
        iso3 = props.get("iso_sov1") or props.get("iso_ter1")
        if not iso3:
            continue
        return {
            "iso2": None,
            "iso3": iso3.upper(),
            "name": props.get("sovereign1") or props.get("territory1") or props.get("geoname"),
            "eez_name": props.get("geoname"),
            "source": f"marine_regions:{layer}",
            "source_url": f"{MARINE_REGIONS_WFS}?typeNames={layer}",
            "confidence": "live",
        }
    return None


def resolve_country(latitude: float, longitude: float) -> dict[str, Any] | None:
    """Step 1 — Resolve a lat/lon to its sovereign country.

    Returns None on the high seas (no sovereign found by either backend).
    The returned dict always carries provenance so the agent can cite it.
    """
    out = _resolve_via_nominatim(latitude, longitude)
    if out and out.get("iso3"):
        out["checked_at"] = _now_iso()
        return out
    out = _resolve_via_marine_regions(latitude, longitude)
    if out:
        out["checked_at"] = _now_iso()
        return out
    return None


# ── Step 2: regulation lookup ────────────────────────────────────────────


@lru_cache(maxsize=64)
def _seeded_faolex_ids(iso3: str) -> tuple[str, ...]:
    """Read finetune/data/seeds/<iso3>.json if present. Cached per process.

    Returns a tuple (hashable, lru-friendly). Empty tuple if no seed file
    or it's empty/malformed — which is the current state for every country.
    """
    path = FINETUNE_DATA / "seeds" / f"{iso3.upper()}.json"
    if not path.exists():
        return ()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    out: list[str] = []
    for item in data:
        if isinstance(item, str):
            out.append(item.upper())
        elif isinstance(item, dict) and "id" in item:
            out.append(str(item["id"]).upper())
    return tuple(out)


_LEX_RE = re.compile(r"LEX-FAO[CS]-?\d{5,8}", re.IGNORECASE)
# IDs that ship with the FAOLEX JS shell regardless of query. Filter them
# out so we don't pretend a country has matches it doesn't.
_FAO_CHROME_IDS = {"LEX-FAOC130388"}


def _try_faolex_search(iso3: str, subject: str) -> dict[str, Any]:
    """Live FAOLEX search → detail pages → gemma3 summary, with disk caching.

    FAOLEX is a SPA whose search params live in a base64-encoded URL fragment
    (`#querystring=<base64>`); plain HTTP returns the JS shell. The crawler
    renders the search SPA via Playwright, then renders each result's
    detail page to capture the actual statute text, then runs gemma3:4b
    over each statute to extract a structured summary (prohibitions /
    gear / area / penalties / IUU relevance / citation quote). The
    enriched records are cached per-country at data/faolex_cache/<iso3>.json
    so subsequent calls for the same country are instant.

    Records sent back to the agent are trimmed: full_text is dropped (kept
    only on disk) so it doesn't blow up the supervisor's context window.
    The structured summary travels — that's what the LLM cites.

    On any browser/LLM failure returns whatever layers it could fill, at
    minimum the search_url so the dossier still has a citation reference.
    """
    from faolex_crawler import crawl_faolex_records

    payload = crawl_faolex_records(iso3, subject=subject)
    trimmed_records = []
    for r in payload.get("records", []):
        trimmed_records.append({
            k: v for k, v in r.items()
            if k != "full_text"  # full_text stays on disk; too long for the agent
        })
    return {
        "search_url": payload["search_url"],
        "ids": [r["id"] for r in payload.get("records", [])],
        "records": trimmed_records,
        "rendered": payload["rendered"],
        "cached": payload.get("cached", False),
        "summarized_count": payload.get("summarized_count", 0),
        "error": payload.get("error"),
    }


def fetch_country_regulations(iso3: str, *, subject: str = "Fisheries") -> dict[str, Any]:
    """Step 2 — Assemble the regulatory dossier for an ISO3 country.

    Layers it tries, in order:
      curated  — backend/data/regional_rules.json (FISHLEX/PORTLEX/FAOLEX)
      seeded   — finetune/data/seeds/<iso3>.json (LEX-FAOC IDs from prior run)
      live     — FAOLEX search URL probe (best-effort over plain HTTP)

    The return shape is uniform regardless of how many layers hit so the
    agent can rely on the same fields. `confidence` reflects the BEST
    layer that contributed (curated > seeded > live).
    """
    iso3 = iso3.upper()
    cached = get_region_by_country(iso3)
    seeded_ids = list(_seeded_faolex_ids(iso3))
    live = _try_faolex_search(iso3, subject)

    if cached:
        confidence = "curated"
    elif seeded_ids:
        confidence = "extracted"
    else:
        confidence = "live"

    out: dict[str, Any] = {
        "country": iso3,
        "subject": subject,
        "checked_at": _now_iso(),
        "confidence": confidence,
        "curated": None,
        "seeded_record_ids": seeded_ids,
        "faolex_search": live,
        "provenance": {
            "primary_source": (
                "regional_rules.json" if cached else
                ("finetune/data/seeds" if seeded_ids else "FAOLEX search URL")
            ),
            "search_url": live["search_url"],
            "checked_at": _now_iso(),
            "confidence": confidence,
        },
    }
    if cached:
        out["curated"] = {
            "id": cached["id"],
            "name": cached["name"],
            "country": cached.get("country"),
            "jurisdiction": cached.get("jurisdiction"),
            "type": cached.get("type"),
            "fishlex": cached.get("fishlex"),
            "portlex": cached.get("portlex"),
            "faolex": cached.get("faolex"),
            "rules": cached.get("rules"),
        }
    return out
