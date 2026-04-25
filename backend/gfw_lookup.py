"""Global Fishing Watch v3 REST client for the IUU risk agent.

Endpoints used:
  GET  /v3/vessels/search       — identity + authorizations + ownership
  POST /v3/insights/vessels     — IUU risk indicators (fused AIS + registry)
  GET  /v3/events               — discrete events (fishing, gap, encounter, ...)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import requests

BASE_URL = "https://gateway.api.globalfishingwatch.org/v3"
VESSEL_DATASET = "public-global-vessel-identity:latest"

EVENT_DATASETS: dict[str, str] = {
    "FISHING": "public-global-fishing-events:latest",
    "ENCOUNTER": "public-global-encounters-events:latest",
    "LOITERING": "public-global-loitering-events:latest",
    "PORT_VISIT": "public-global-port-visits-events:latest",
    "GAP": "public-global-gaps-events:latest",
}

DEFAULT_INSIGHT_INCLUDES = ["FISHING", "GAP", "COVERAGE", "VESSEL-IDENTITY-IUU-VESSEL-LIST"]

# GFW selfReportedInfo.shiptypes values that indicate a fishing-capable vessel.
# Strictly "FISHING"; carriers/bunkers/supports enable IUU but are not themselves
# fishing vessels per AIS / GFW classification.
_FISHING_SHIP_TYPES = {"FISHING"}


@dataclass
class VesselRecord:
    vessel_id: str
    mmsi: str | None
    name: str | None
    flag: str | None
    imo: str | None
    callsign: str | None
    ship_type: str | None
    gear_type: str | None
    owners: list[dict[str, Any]] = field(default_factory=list)
    authorizations: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def _headers() -> dict[str, str]:
    token = os.getenv("GFW_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "GFW_API_TOKEN is not set. Request a token at "
            "https://globalfishingwatch.org/our-apis/ and add it to your .env."
        )
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _first(items: Any) -> str | None:
    if isinstance(items, list) and items:
        head = items[0]
        return head if isinstance(head, str) else str(head)
    return None


def _parse_vessel(entry: dict[str, Any]) -> VesselRecord:
    self_reported = entry.get("selfReportedInfo") or []
    sr = self_reported[-1] if self_reported else {}
    return VesselRecord(
        vessel_id=sr.get("id") or entry.get("vesselId") or entry.get("id") or "",
        mmsi=sr.get("ssvid"),
        name=sr.get("shipname"),
        flag=sr.get("flag"),
        imo=sr.get("imo"),
        callsign=sr.get("callsign"),
        ship_type=_first(sr.get("shiptypes")),
        gear_type=_first(sr.get("geartypes")),
        owners=entry.get("registryOwners") or [],
        authorizations=entry.get("registryPublicAuthorizations") or [],
        raw=entry,
    )


def pick_best_vessel(
    records: list[VesselRecord],
    query: str | None = None,
) -> VesselRecord | None:
    """Pick the most useful vessel record from a search.

    Honors the query intent first (exact MMSI match, then exact name match,
    then strong prefix match), falling back to a completeness ranking.
    Skips placeholder records (MMSIs starting with 9999) when other options
    exist.
    """
    if not records:
        return None
    real = [
        r for r in records
        if r.mmsi and not r.mmsi.startswith("9999") and r.flag
    ]
    pool = real or records

    if query:
        q = query.strip().upper()
        if query.isdigit():
            mmsi_hit = [r for r in pool if r.mmsi == query]
            if mmsi_hit:
                return mmsi_hit[0]
        exact_name = [r for r in pool if r.name and r.name.strip().upper() == q]
        if exact_name:
            return max(
                exact_name,
                key=lambda r: (len(r.authorizations), len(r.owners), bool(r.imo)),
            )
        prefix_name = [r for r in pool if r.name and r.name.strip().upper().startswith(q)]
        if prefix_name:
            return max(
                prefix_name,
                key=lambda r: (len(r.authorizations), len(r.owners), bool(r.imo)),
            )

    return max(pool, key=lambda r: (len(r.authorizations), len(r.owners), bool(r.imo)))


def is_fishing_vessel(record: VesselRecord) -> bool:
    """True if a GFW vessel-identity record describes a fishing-capable vessel.

    Two signals from GFW selfReportedInfo:
      - geartypes is set (PURSE_SEINES, TRAWLERS, POTS_AND_TRAPS, ...) — the
        vessel carries fishing gear, so it is a fishing vessel by construction.
      - shiptypes contains "FISHING" (the broad GFW class).

    Carriers, bunkers, support vessels, tankers and cargo ships return False
    even though they may participate in IUU operations — the IUU classifier
    pipeline is scoped to *fishing vessels* per the user requirement.
    """
    if record.gear_type and str(record.gear_type).strip():
        return True
    if record.ship_type and str(record.ship_type).strip().upper() in _FISHING_SHIP_TYPES:
        return True
    return False


def search_vessel(query: str, limit: int = 10) -> list[VesselRecord]:
    params = [
        ("query", query),
        ("datasets[0]", VESSEL_DATASET),
        ("includes[0]", "OWNERSHIP"),
        ("includes[1]", "AUTHORIZATIONS"),
        ("limit", str(limit)),
    ]
    resp = requests.get(
        f"{BASE_URL}/vessels/search",
        params=params,
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    return [_parse_vessel(entry) for entry in payload.get("entries", [])]


def get_vessel_insights(
    vessel_id: str,
    start_date: str,
    end_date: str,
    includes: list[str] | None = None,
) -> dict[str, Any]:
    body = {
        "includes": includes or DEFAULT_INSIGHT_INCLUDES,
        "startDate": start_date,
        "endDate": end_date,
        "vessels": [{"vesselId": vessel_id, "datasetId": VESSEL_DATASET}],
    }
    resp = requests.post(
        f"{BASE_URL}/insights/vessels",
        json=body,
        headers=_headers(),
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def get_vessel_events(
    vessel_id: str,
    event_type: str,
    start_date: str,
    end_date: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if event_type not in EVENT_DATASETS:
        raise ValueError(
            f"Unknown event type {event_type!r}; expected one of {list(EVENT_DATASETS)}"
        )
    params = [
        ("vessels[0]", vessel_id),
        ("datasets[0]", EVENT_DATASETS[event_type]),
        ("start-date", start_date),
        ("end-date", end_date),
        ("limit", str(limit)),
        ("offset", "0"),
    ]
    resp = requests.get(
        f"{BASE_URL}/events",
        params=params,
        headers=_headers(),
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get("entries", [])


def get_events_in_region(
    bbox: tuple[float, float, float, float],
    event_type: str = "FISHING",
    start_date: str = "",
    end_date: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Query GFW Events for events of `event_type` whose position falls in `bbox`.

    `bbox` is (lat_min, lon_min, lat_max, lon_max). Returns the same event-dict
    shape as `get_vessel_events`, so each entry exposes `vessel.ssvid` (MMSI)
    plus `start`, `end`, `position`. Used by the pipeline as the AIS-silent
    fallback to surface vessels that GFW saw active in a region even when
    AISStream is silent.
    """
    if event_type not in EVENT_DATASETS:
        raise ValueError(
            f"Unknown event type {event_type!r}; expected one of {list(EVENT_DATASETS)}"
        )
    lat_min, lon_min, lat_max, lon_max = bbox
    polygon = {
        "type": "Polygon",
        "coordinates": [[
            [lon_min, lat_min],
            [lon_max, lat_min],
            [lon_max, lat_max],
            [lon_min, lat_max],
            [lon_min, lat_min],
        ]],
    }
    body = {
        "datasets": [EVENT_DATASETS[event_type]],
        "startDate": start_date,
        "endDate": end_date,
        "geometry": polygon,
    }
    params = {"limit": limit, "offset": 0}
    resp = requests.post(
        f"{BASE_URL}/events",
        params=params,
        json=body,
        headers=_headers(),
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json().get("entries", [])


def extract_mmsi(event: dict[str, Any]) -> str | None:
    """Pull the MMSI from a GFW event entry. Shape varies slightly across endpoints."""
    vessel = event.get("vessel") or {}
    return (
        vessel.get("ssvid")
        or vessel.get("mmsi")
        or event.get("ssvid")
        or event.get("mmsi")
    )


SAR_DATASET = "public-global-sar-presence:latest"


def get_sar_detections_in_region(
    bbox: tuple[float, float, float, float],
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Query GFW 4Wings for SAR (Sentinel-1 satellite radar) vessel detections in a bbox.

    `bbox` is (lat_min, lon_min, lat_max, lon_max). Returns the raw 4Wings
    report payload — typically `{"entries": [{"datasetId": ..., "value": <count>}]}`
    or a similar aggregated form.

    SAR detects vessels by radar reflection regardless of whether they broadcast
    AIS, so this is the path to find AIS-dark vessels. The response carries no
    MMSI/identity — SAR can't capture broadcasts. Cross-reference the count
    with the AIS-broadcast count from vessel_lookup to identify dark targets.
    """
    lat_min, lon_min, lat_max, lon_max = bbox
    polygon = {
        "type": "Polygon",
        "coordinates": [[
            [lon_min, lat_min],
            [lon_max, lat_min],
            [lon_max, lat_max],
            [lon_min, lat_max],
            [lon_min, lat_min],
        ]],
    }
    body = {
        "geojson": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": polygon,
                    "properties": {},
                }
            ],
        }
    }
    params = [
        ("datasets[0]", SAR_DATASET),
        ("date-range", f"{start_date},{end_date}"),
        ("format", "JSON"),
        ("spatial-resolution", "LOW"),
        ("temporal-resolution", "ENTIRE"),
        # Exclude vessels GFW's neural net classifies as "Likely non-fishing"
        # (≤0.1). The column is stored as a string in GFW's ClickHouse, so we
        # cast — `toFloat64OrZero` returns 0 on empty/non-numeric, which the
        # ≥0.1 threshold then filters out. Result: only fishing-likely or
        # other/unknown detections are counted; cargo, ferries, yachts dropped.
        ("filters[0]", "toFloat64OrZero(neural_vessel_type)>=0.1"),
    ]
    resp = requests.post(
        f"{BASE_URL}/4wings/report",
        params=params,
        json=body,
        headers=_headers(),
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()


def sar_detection_count(payload: dict[str, Any]) -> int | None:
    """Best-effort extract a single integer count from a 4Wings SAR report.

    Handles several GFW response shapes:
    - `{"entries": [{"public-global-sar-presence:v4.0": <N or null>}]}` — versioned key
    - `{"entries": [{"value": N}]}` — named key
    - `{"total": N}` — top-level total
    Returns 0 when entries exist but all values are null (confirmed zero detections).
    Returns None only when the shape is completely unrecognised.
    """
    if not payload:
        return None

    # Top-level shortcut keys
    for key in ("value", "count", "detections"):
        v = payload.get(key)
        if isinstance(v, (int, float)):
            return int(v)

    entries = payload.get("entries")
    if isinstance(entries, list) and entries:
        total = 0
        has_any_entry = False
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            has_any_entry = True
            # Try well-known scalar keys first
            for k in ("value", "count", "detections", "hours"):
                v = entry.get(k)
                if isinstance(v, (int, float)):
                    total += int(v)
                    break
            else:
                # Fall back to any numeric value in the dict (handles versioned-key shape)
                for v in entry.values():
                    if isinstance(v, (int, float)):
                        total += int(v)
                        break
        if has_any_entry:
            return total  # 0 means confirmed zero detections (all null)

    # Last resort: top-level "total" (GFW uses this for record counts, not detection counts,
    # but better than returning None when shape is otherwise empty)
    total_v = payload.get("total")
    if isinstance(total_v, (int, float)):
        return int(total_v)

    return None
