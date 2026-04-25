"""Species → fishery region exposure for hackathon demo (fixture-only).

Joins curated species–region links to ``fishery_regions`` risk labels. Sorts by
IUU-style risk severity (descending). Not catch-weighted or peer-reviewed.
"""

from __future__ import annotations

import os
from typing import Any

from fixtures._loader import load_raw

_USE_FIXTURES = os.getenv("USE_FIXTURES", "1") == "1"

_RISK_ORDER: dict[str, int] = {
    "confirmed_iuu": 4,
    "high_risk": 3,
    "suspect": 2,
    "safe": 1,
}

ALLOWED_SPECIES = frozenset({"cod", "salmon", "trout"})

DISCLAIMER = (
    "Illustrative only: links each species to demo fishery polygons and their "
    "IUU-style risk labels— not catch composition, stock assessment, or reviewed science."
)


def get_species_fishing_exposure(species: str) -> dict[str, Any]:
    if not _USE_FIXTURES:
        raise NotImplementedError("Species exposure is only implemented in fixture mode (USE_FIXTURES=1).")

    key = species.strip().lower()
    if key not in ALLOWED_SPECIES:
        raise ValueError(f"Unknown species {species!r}; allowed: {', '.join(sorted(ALLOWED_SPECIES))}.")

    exposure: dict[str, list[dict[str, str]]] = load_raw("species_fishery_exposure")  # type: ignore[assignment]
    rows = exposure.get(key)
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"No exposure rows configured for species {key!r}.")

    fishery_list: list[dict[str, Any]] = load_raw("fishery_regions")  # type: ignore[assignment]
    by_id = {r["region_id"]: r for r in fishery_list if isinstance(r, dict) and "region_id" in r}

    merged: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        rid = row.get("region_id")
        note = row.get("species_note", "")
        base = by_id.get(str(rid))
        if base is None:
            raise ValueError(f"Unknown region_id {rid!r} in species_fishery_exposure for {key}.")
        risk = str(base["risk"])
        merged.append(
            {
                "region_id": base["region_id"],
                "name": base["name"],
                "risk": risk,
                "species_note": str(note),
                "geometry": base["geometry"],
                "_sort": _RISK_ORDER.get(risk, 0),
            }
        )

    merged.sort(key=lambda x: x["_sort"], reverse=True)
    for m in merged:
        del m["_sort"]

    features: list[dict[str, Any]] = []
    for m in merged:
        geom = m.pop("geometry")
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "region_id": m["region_id"],
                    "name": m["name"],
                    "risk": m["risk"],
                    "species_note": m["species_note"],
                },
            }
        )

    return {
        "species": key,
        "disclaimer": DISCLAIMER,
        "regions": merged,
        "geojson": {"type": "FeatureCollection", "features": features},
    }
