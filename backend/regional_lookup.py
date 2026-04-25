"""Regional fishing-law lookup backed by a curated FAOLEX/FISHLEX/PORTLEX cache.

The cache lives at `data/regional_rules.json` and currently covers three
demo regions:
  - galapagos-marine-reserve    (Ecuador / GMR + Hermandad)
  - philippines-eez             (Philippines EEZ + Tubbataha + closed seasons)
  - eu-western-mediterranean    (EU + GFCM management area)

A `bbox` on each region powers point-in-region resolution from coordinates.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).parent / "data" / "regional_rules.json"


@lru_cache(maxsize=1)
def _load_rules() -> list[dict[str, Any]]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _bbox_contains(bbox: dict[str, float], lat: float, lon: float) -> bool:
    return (
        bbox.get("lat_min", -91) <= lat <= bbox.get("lat_max", 91)
        and bbox.get("lon_min", -181) <= lon <= bbox.get("lon_max", 181)
    )


def identify_region(latitude: float, longitude: float) -> dict[str, Any] | None:
    for region in _load_rules():
        if _bbox_contains(region.get("bbox") or {}, latitude, longitude):
            return region
    return None


def get_region_by_id(region_id: str) -> dict[str, Any] | None:
    for region in _load_rules():
        if region.get("id") == region_id:
            return region
    return None


def get_region_by_country(country_code: str) -> dict[str, Any] | None:
    code = country_code.upper()
    for region in _load_rules():
        if (region.get("country") or "").upper() == code:
            return region
    return None


def list_regions() -> list[dict[str, Any]]:
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "country": r.get("country"),
            "jurisdiction": r.get("jurisdiction"),
            "level_of_fishing_protection": r.get("level_of_fishing_protection"),
            "bbox": r.get("bbox"),
        }
        for r in _load_rules()
    ]
