"""Vessel & event lookups.

Real mode wraps the GFW 4Wings / Vessels / Events APIs (pending teammate's GFW
token). Fixture mode reads from ``backend/fixtures/`` and is the demo default.

The heatmap and track endpoints return raw lists (not Pydantic) because globe.gl
consumes them directly — adding a wrapper schema is overhead with no benefit.
"""

from __future__ import annotations

import os
from datetime import datetime

from fixtures._loader import load_model, load_models, load_raw
from tools.schemas import LatLon, Vessel, VesselEvent

_USE_FIXTURES = os.getenv("USE_FIXTURES", "1") == "1"


def get_vessels_in_region(
    region_id: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    min_fishing_hours: float = 0.0,
) -> list[Vessel]:
    """Vessels with at least ``min_fishing_hours`` of activity in the region."""
    if _USE_FIXTURES:
        return load_models("vessels_galapagos", Vessel)
    raise NotImplementedError("set USE_FIXTURES=1")


def get_vessel_info(mmsi: str) -> Vessel:
    """Identity + ownership + authorizations for a single MMSI."""
    if _USE_FIXTURES:
        vessels = load_models("vessels_galapagos", Vessel)
        match = next((v for v in vessels if v.mmsi == mmsi), None)
        if match is None:
            raise ValueError(f"No fixture for MMSI {mmsi!r}")
        return match
    raise NotImplementedError("set USE_FIXTURES=1")


def get_vessel_events(
    mmsi: str,
    event_types: list[str] | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[VesselEvent]:
    """Behavioural events (FISHING, GAP, ENCOUNTER, LOITERING, PORT_VISIT)."""
    if _USE_FIXTURES:
        if mmsi != "412345678":
            return []
        events = load_models(f"events_{mmsi}", VesselEvent)
        if event_types:
            events = [e for e in events if e.type in event_types]
        return events
    raise NotImplementedError("set USE_FIXTURES=1")


def get_vessel_track(mmsi: str, hours: int = 24) -> list[list[float]]:
    """Position history as ``[[lat, lng], ...]`` — feeds globe.gl Paths layer."""
    if _USE_FIXTURES:
        if mmsi != "412345678":
            return []
        return load_raw(f"track_{mmsi}")  # type: ignore[return-value]
    raise NotImplementedError("set USE_FIXTURES=1")


def get_fishing_effort_heatmap(
    region_id: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    resolution: str = "HIGH",
) -> list[dict]:
    """Fishing-effort cells as ``[{lat, lon, hours}, ...]`` — feeds globe.gl Heatmaps."""
    if _USE_FIXTURES:
        return load_raw("heatmap_galapagos")  # type: ignore[return-value]
    raise NotImplementedError("set USE_FIXTURES=1")


def get_global_vessel_tracks() -> list[dict]:
    """Return vessel tracks worldwide for the ambient Paths layer.

    Each entry has ``{mmsi, name, flag, risk, points: [[lat,lng], ...]}``.
    Frontend renders these as 3D ship meshes interpolating along the points
    (see ``frontend/src/components/useAnimatedFleet.ts``).

    Source priority:
      1. ``vessel_tracks_global.json`` — written by ``tools.gfw_prefetch``,
         contains real GFW AIS Vessel Presence data when the prefetch has
         been run with a valid token.
      2. ``vessel_tracks_global.fallback.json`` — committed procedural data,
         used if the GFW cache is missing or empty so the demo never shows
         an empty globe.

    The runtime never calls GFW directly — see plan in
    ``/Users/chanyeong/.claude/plans/gfw-real-vessel-tracks.md``.
    """
    if _USE_FIXTURES:
        try:
            data = load_raw("vessel_tracks_global")
            if data:
                return data  # type: ignore[return-value]
        except FileNotFoundError:
            pass
        return load_raw("vessel_tracks_global.fallback")  # type: ignore[return-value]
    raise NotImplementedError("set USE_FIXTURES=1")


def get_vessel_iuu_insights(mmsi: str) -> dict:
    """GFW Insights API stand-in — one input to risk.calculate_risk."""
    if _USE_FIXTURES:
        if mmsi == "412345678":
            return {
                "mmsi": mmsi,
                "ais_off_events_90d": 1,
                "encounters_90d": 0,
                "loitering_events_90d": 1,
                "port_visits_to_iuu_listed_ports_90d": 1,
                "flag_state_iuu_risk": "elevated",
                "prior_listings": [],
            }
        return {
            "mmsi": mmsi,
            "ais_off_events_90d": 0,
            "encounters_90d": 0,
            "loitering_events_90d": 0,
            "port_visits_to_iuu_listed_ports_90d": 0,
            "flag_state_iuu_risk": "low",
            "prior_listings": [],
        }
    raise NotImplementedError("set USE_FIXTURES=1")
