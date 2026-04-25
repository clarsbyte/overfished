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
