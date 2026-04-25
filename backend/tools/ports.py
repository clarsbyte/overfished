"""Port lookup + port-state denial via Bland AI outbound call."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from tools.schemas import CaseFile

_USE_FIXTURES = os.getenv("USE_FIXTURES", "1") == "1"

# Demo port directory — covers the two ports the document family addresses.
_PORTS = {
    "PE CLL": {
        "un_locode": "PE CLL",
        "name": "Callao",
        "country": "PER",
        "lat": -12.0464,
        "lon": -77.1428,
        "facilities": ["transshipment", "repair", "fuel"],
    },
    "EC MEC": {
        "un_locode": "EC MEC",
        "name": "Manta",
        "country": "ECU",
        "lat": -0.9485,
        "lon": -80.7256,
        "facilities": ["fishing", "transshipment", "container"],
    },
}


def lookup_port(name_or_locode: str) -> dict | None:
    """World Port Index stand-in. Match on UN/LOCODE or case-insensitive name."""
    if _USE_FIXTURES:
        key = name_or_locode.upper()
        if key in _PORTS:
            return _PORTS[key]
        for port in _PORTS.values():
            if port["name"].upper() == key:
                return port
        return None
    raise NotImplementedError("set USE_FIXTURES=1")


def predict_next_port(mmsi: str, top_k: int = 3) -> list[dict]:
    """Most-frequented ports in the last 90 days, weighted by recency."""
    if _USE_FIXTURES:
        if mmsi == "412345678":
            # Order matches PSMA notification chain in notice_of_violation.html.
            return [
                {**_PORTS["EC MEC"], "weight": 0.62, "predicted_eta_iso": _eta(36)},
                {**_PORTS["PE CLL"], "weight": 0.31, "predicted_eta_iso": _eta(72)},
            ][:top_k]
        return []
    raise NotImplementedError("set USE_FIXTURES=1")


def notify_port_authority(
    port: dict,
    case: CaseFile,
    test_phone_number: str,
) -> dict:
    """Initiate an outbound Bland AI call to the test phone."""
    if _USE_FIXTURES:
        # TODO(chan): wire Bland once API key + verified number are set.
        return {
            "call_id": f"bland-fixture-{case.case_id}",
            "status": "QUEUED",
            "to_number": test_phone_number,
            "port": {"name": port["name"], "un_locode": port["un_locode"]},
            "recording_url": f"/static/audio/portcall_{case.case_id}.mp3",
        }
    raise NotImplementedError("set USE_FIXTURES=1")


def _eta(hours: int) -> str:
    """Helper: ISO timestamp ``hours`` from the demo's reference moment."""
    base = datetime(2026, 4, 18, 11, 27, tzinfo=timezone.utc)
    return (base + timedelta(hours=hours)).isoformat()
