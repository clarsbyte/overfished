"""Source-prioritized regional fishing-law lookup.

Geospatial layer (live):
  - ProtectedSeas Navigator Global Max LFP FeatureServer
    -> point  →  Level of Fishing Protection (1–5) + provenance

Legal layer (curated cache; would be replaced by upstream ingestion):
  - FISHLEX  →  per-country foreign-vessel rules
  - PORTLEX  →  per-country port state measures
  - FAOLEX   →  source law records (titles, year, search/permalink URLs)

Coordinate → coastal state is currently a coarse bbox lookup against the
cache. Production should swap this for a polygon query against the Marine
Regions World EEZ layer; the surrounding API does not change.

Every returned object carries a `provenance` block so the agent can cite:
  database, source_url, last_checked, confidence ∈ {live, curated, extracted}
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from protectedseas_arcgis import query_lfp_at_point


def _rag_enabled() -> bool:
    return os.getenv("RAG_FINETUNE", "").strip().lower() in {"1", "true", "yes", "on"}

DATA_PATH = Path(__file__).parent / "data" / "regional_rules.json"


@lru_cache(maxsize=1)
def _load_cache() -> list[dict[str, Any]]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _bbox_contains(bbox: dict[str, float], lat: float, lon: float) -> bool:
    return (
        bbox.get("lat_min", -91) <= lat <= bbox.get("lat_max", 91)
        and bbox.get("lon_min", -181) <= lon <= bbox.get("lon_max", 181)
    )


def identify_coastal_state(latitude: float, longitude: float) -> dict[str, Any] | None:
    """Resolve a coordinate to a cached coastal-state region via bbox lookup.

    Returns the region cache entry (with FISHLEX/PORTLEX/FAOLEX blocks intact),
    or None if the point is outside every cached bbox.

    NOTE: This is a stub for the EEZ-polygon query. The agent treats a None
    result as "coastal state unknown — declare INSUFFICIENT DATA" rather than
    inventing rules.
    """
    for region in _load_cache():
        if _bbox_contains(region.get("bbox") or {}, latitude, longitude):
            return region
    return None


def get_region_by_id(region_id: str) -> dict[str, Any] | None:
    for region in _load_cache():
        if region.get("id") == region_id:
            return region
    return None


def get_region_by_country(country_code: str) -> dict[str, Any] | None:
    code = country_code.upper()
    for region in _load_cache():
        if (region.get("country") or "").upper() == code:
            return region
    return None


def list_cached_regions() -> list[dict[str, Any]]:
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "country": r.get("country"),
            "jurisdiction": r.get("jurisdiction"),
            "bbox": r.get("bbox"),
            "type": r.get("type"),
        }
        for r in _load_cache()
    ]


def geospatial_overlay(latitude: float, longitude: float) -> dict[str, Any]:
    """Run the live geospatial layer for a coordinate.

    Today: ProtectedSeas Global Max LFP. Future additions (Marine Regions EEZ,
    GFW global fishing-effort heatmap) plug into this function.
    """
    lfp = query_lfp_at_point(latitude, longitude)
    return {
        "coordinate": {"latitude": latitude, "longitude": longitude},
        "protectedseas": lfp,
    }


def assemble_legal_dossier(
    latitude: float,
    longitude: float,
    port_country_code: str | None = None,
) -> dict[str, Any]:
    """Top-level composer: geospatial overlay + coastal-state legal layer + (optional) port state.

    Pipeline:
      1. Geospatial overlay (live ProtectedSeas).
      2. Coastal state — bbox cache first, then live (Nominatim → Marine
         Regions EEZ) reverse-geocode, then a regulation-layer fetch
         (curated cache → seeded FAOLEX IDs → FAOLEX search URL).
      3. Port state — by ISO3, falls through to the same regulation-layer
         fetch when the port country is outside the curated cache.

    Step 2's two-stage chase is what makes the dossier useful for any
    coastal coordinate, not just the three demo regions in
    backend/data/regional_rules.json.

    Every section carries its own `provenance`; the assembler adds an outer
    `assembled_at` timestamp so the LLM can include "last checked" in
    citations.
    """
    # Lazy import: country_lookup imports regional_lookup, so importing it
    # at module level would create a circular dependency.
    from country_lookup import fetch_country_regulations, resolve_country

    overlay = geospatial_overlay(latitude, longitude)
    coastal = identify_coastal_state(latitude, longitude)

    coastal_block: dict[str, Any] | None = None
    if coastal:
        coastal_block = {
            "id": coastal["id"],
            "name": coastal["name"],
            "country": coastal.get("country"),
            "jurisdiction": coastal.get("jurisdiction"),
            "type": coastal.get("type"),
            "fishlex": coastal.get("fishlex"),
            "faolex": coastal.get("faolex"),
            "rules": coastal.get("rules"),
            "provenance": {"source": "regional_rules.json (bbox)", "confidence": "curated"},
        }
    else:
        # Live two-step fallback: who owns this point, and what's their FAOLEX?
        country = resolve_country(latitude, longitude)
        if country and country.get("iso3"):
            regs = fetch_country_regulations(country["iso3"])
            curated = regs.get("curated")
            coastal_block = {
                "id": (curated or {}).get("id") or f"live:{country['iso3']}",
                "name": (curated or {}).get("name") or country.get("name") or country["iso3"],
                "country": country["iso3"],
                "country_resolution": {
                    "source": country["source"],
                    "source_url": country["source_url"],
                    "checked_at": country["checked_at"],
                },
                "jurisdiction": (curated or {}).get("jurisdiction"),
                "type": (curated or {}).get("type"),
                "fishlex": (curated or {}).get("fishlex"),
                "faolex": (curated or {}).get("faolex"),
                "rules": (curated or {}).get("rules"),
                "regulations_search": regs["faolex_search"],
                "seeded_record_ids": regs["seeded_record_ids"],
                "provenance": regs["provenance"],
            }

    port_block: dict[str, Any] | None = None
    if port_country_code:
        port = get_region_by_country(port_country_code)
        if port:
            port_block = {
                "id": port["id"],
                "name": port["name"],
                "country": port.get("country"),
                "portlex": port.get("portlex"),
                "provenance": {"source": "regional_rules.json", "confidence": "curated"},
            }
        else:
            iso3 = port_country_code.upper()
            # If the port country is the same as the coastal-state country
            # we just resolved live, the FAOLEX records are identical —
            # don't re-fetch and don't duplicate the payload (the LLM's
            # context can't take a 2x copy of the same 10 records).
            if (
                coastal_block
                and coastal_block.get("country") == iso3
                and coastal_block.get("regulations_search")
            ):
                port_block = {
                    "id": f"live:{iso3}",
                    "name": iso3,
                    "country": iso3,
                    "portlex": None,
                    "regulations_search_ref": (
                        "see coastal_state.regulations_search "
                        "(same country — records not duplicated)"
                    ),
                    "provenance": coastal_block["provenance"],
                }
            else:
                from country_lookup import fetch_country_regulations as _fetch
                regs = _fetch(iso3)
                port_block = {
                    "id": f"live:{iso3}",
                    "name": iso3,
                    "country": iso3,
                    "portlex": None,
                    "regulations_search": regs["faolex_search"],
                    "seeded_record_ids": regs["seeded_record_ids"],
                    "provenance": regs["provenance"],
                }

    return {
        "assembled_at": datetime.now(timezone.utc).isoformat(),
        "geospatial": overlay,
        "coastal_state": coastal_block,
        "port_state": port_block,
        "missing": _missing_layers(overlay, coastal_block, port_block),
    }


def _missing_layers(
    overlay: dict[str, Any],
    coastal: dict[str, Any] | None,
    port: dict[str, Any] | None,
) -> list[str]:
    gaps: list[str] = []
    ps = (overlay or {}).get("protectedseas") or {}
    if not ps.get("matched"):
        gaps.append("protectedseas: point did not intersect any LFP polygon (open-water or sub-LFP-1).")
    if coastal is None:
        gaps.append("coastal_state: high seas — no sovereign EEZ; only flag-state and RFMO rules apply.")
    elif coastal.get("rules") is None and coastal.get("fishlex") is None:
        # Country resolved but no curated dossier — operator should follow the FAOLEX search URL.
        gaps.append(
            f"coastal_state: country {coastal.get('country')} resolved live but is not in the "
            f"curated FISHLEX/FAOLEX cache — follow regulations_search.search_url for source records."
        )
    if port is None:
        gaps.append("port_state: no port country supplied.")
    elif port.get("portlex") is None:
        gaps.append(
            f"port_state: port country {port.get('country')} is not in the curated PORTLEX cache — "
            f"follow regulations_search.search_url for source records."
        )
    return gaps
