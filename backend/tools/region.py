"""Region & geography tools.

Real mode would call Marine Regions (EEZ shapefile point-in-polygon) and
Protected Planet (MPA lookup). Fixture mode ignores arguments and returns the
pre-baked Galápagos demo region — every drawn polygon resolves to it during
the demo, which is exactly what we want for a deterministic showcase.
"""

from __future__ import annotations

import os

from fixtures._loader import load_model, load_raw
from tools.schemas import LatLon, RegionContext

_USE_FIXTURES = os.getenv("USE_FIXTURES", "1") == "1"


def define_region(polygon: dict) -> RegionContext:
    """Resolve a user-drawn GeoJSON polygon into a populated RegionContext."""
    if _USE_FIXTURES:
        return load_model("region_galapagos", RegionContext)
    raise NotImplementedError("set USE_FIXTURES=1")


def lookup_eez(point: LatLon) -> str | None:
    """Return ISO3 of the EEZ at ``point``, or None for high seas."""
    if _USE_FIXTURES:
        # Demo: Galápagos EEZ for any point within the demo bounding box.
        if -2.0 <= point.lat <= 2.0 and -92.0 <= point.lon <= -89.0:
            return "ECU"
        return None
    raise NotImplementedError("set USE_FIXTURES=1")


def get_fishery_regions() -> list[dict]:
    """Return named fishery regions worldwide for the hex-polygons risk overlay.

    Each entry has ``{region_id, name, risk, geometry}`` where ``geometry`` is a
    GeoJSON Polygon and ``risk`` is one of confirmed_iuu | high_risk | suspect | safe.
    """
    if _USE_FIXTURES:
        return load_raw("fishery_regions")  # type: ignore[return-value]
    raise NotImplementedError("set USE_FIXTURES=1")


def lookup_mpas_in_region(region_id: str) -> list[dict]:
    """Return overlapping marine protected areas with WDPA metadata."""
    if _USE_FIXTURES:
        if region_id == "galapagos":
            return [
                {
                    "wdpa_id": 11765,
                    "name": "Galápagos Marine Reserve",
                    "iucn_category": "II",
                    "country": "ECU",
                    "marine_area_km2": 133000.0,
                    "designation": "Marine Reserve",
                }
            ]
        return []
    raise NotImplementedError("set USE_FIXTURES=1")
