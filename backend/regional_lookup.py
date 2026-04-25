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
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from protectedseas_arcgis import query_lfp_at_point

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

    Returns a single document the agent's tools can serialize. Every section
    carries its own `provenance`; the assembler adds an outer `assembled_at`
    timestamp so the LLM can include "last checked" in citations.
    """
    overlay = geospatial_overlay(latitude, longitude)
    coastal = identify_coastal_state(latitude, longitude)
    port = get_region_by_country(port_country_code) if port_country_code else None

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
        }

    port_block: dict[str, Any] | None = None
    if port:
        port_block = {
            "id": port["id"],
            "name": port["name"],
            "country": port.get("country"),
            "portlex": port.get("portlex"),
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
        gaps.append("coastal_state: coordinate outside cached coastal-state bboxes — EEZ polygon lookup not yet wired.")
    if port is None:
        gaps.append("port_state: no port country supplied or port not in cache.")
    return gaps
