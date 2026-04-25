"""Port lookup + port-state denial via Bland AI outbound call."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from tools.schemas import CaseFile

_USE_FIXTURES = os.getenv("USE_FIXTURES", "1") == "1"

# Curated global port directory used as the fallback for find_nearest_port
# when GFW PORT_VISIT events are sparse (remote MPAs, AIS-dark zones). Covers
# the major fishing / port-state ports across each maritime region. Coordinates
# are approximate harbour entrances (decimal degrees).
_PORTS = {
    # Pacific — South America
    "PE CLL": {"un_locode": "PE CLL", "name": "Callao",        "country": "PER", "lat": -12.0464, "lon":  -77.1428, "facilities": ["transshipment", "repair", "fuel"]},
    "PE PAI": {"un_locode": "PE PAI", "name": "Paita",         "country": "PER", "lat":  -5.0892, "lon":  -81.1144, "facilities": ["fishing"]},
    "EC MEC": {"un_locode": "EC MEC", "name": "Manta",         "country": "ECU", "lat":  -0.9485, "lon":  -80.7256, "facilities": ["fishing", "transshipment", "container"]},
    "EC GYE": {"un_locode": "EC GYE", "name": "Guayaquil",     "country": "ECU", "lat":  -2.2740, "lon":  -79.8800, "facilities": ["container", "fuel"]},
    "CL VAP": {"un_locode": "CL VAP", "name": "Valparaíso",    "country": "CHL", "lat": -33.0357, "lon":  -71.6207, "facilities": ["container", "fishing"]},
    "MX ZLO": {"un_locode": "MX ZLO", "name": "Manzanillo",    "country": "MEX", "lat":  19.0541, "lon": -104.3175, "facilities": ["container", "fishing"]},
    "MX ESE": {"un_locode": "MX ESE", "name": "Ensenada",      "country": "MEX", "lat":  31.8500, "lon": -116.6230, "facilities": ["fishing"]},
    # Pacific — North America
    "US LAX": {"un_locode": "US LAX", "name": "Los Angeles",   "country": "USA", "lat":  33.7400, "lon": -118.2700, "facilities": ["container", "fuel"]},
    "US SFO": {"un_locode": "US SFO", "name": "San Francisco", "country": "USA", "lat":  37.8000, "lon": -122.4000, "facilities": ["container"]},
    "US SEA": {"un_locode": "US SEA", "name": "Seattle",       "country": "USA", "lat":  47.6097, "lon": -122.3331, "facilities": ["container", "fishing"]},
    "US DUT": {"un_locode": "US DUT", "name": "Dutch Harbor",  "country": "USA", "lat":  53.8910, "lon": -166.5430, "facilities": ["fishing"]},
    "US HNL": {"un_locode": "US HNL", "name": "Honolulu",      "country": "USA", "lat":  21.3070, "lon": -157.8650, "facilities": ["container", "fishing"]},
    "CA VAN": {"un_locode": "CA VAN", "name": "Vancouver",     "country": "CAN", "lat":  49.2900, "lon": -123.1100, "facilities": ["container", "fishing"]},
    # Pacific — Asia
    "PH MNL": {"un_locode": "PH MNL", "name": "Manila",        "country": "PHL", "lat":  14.5800, "lon": 120.9700, "facilities": ["container", "fishing"]},
    "PH NAV": {"un_locode": "PH NAV", "name": "Navotas",       "country": "PHL", "lat":  14.6700, "lon": 120.9450, "facilities": ["fishing"]},
    "PH GES": {"un_locode": "PH GES", "name": "General Santos","country": "PHL", "lat":   6.1100, "lon": 125.1700, "facilities": ["fishing", "transshipment"]},
    "PH CEB": {"un_locode": "PH CEB", "name": "Cebu",          "country": "PHL", "lat":  10.3000, "lon": 123.9000, "facilities": ["container", "fishing"]},
    "PH DVO": {"un_locode": "PH DVO", "name": "Davao",         "country": "PHL", "lat":   7.0700, "lon": 125.6100, "facilities": ["container", "fishing"]},
    "PH ZAM": {"un_locode": "PH ZAM", "name": "Zamboanga",     "country": "PHL", "lat":   6.9100, "lon": 122.0750, "facilities": ["fishing"]},
    "ID JKT": {"un_locode": "ID JKT", "name": "Jakarta",       "country": "IDN", "lat":  -6.1100, "lon": 106.8800, "facilities": ["container"]},
    "ID BIT": {"un_locode": "ID BIT", "name": "Bitung",        "country": "IDN", "lat":   1.4400, "lon": 125.1900, "facilities": ["fishing", "transshipment"]},
    "ID DPS": {"un_locode": "ID DPS", "name": "Benoa",         "country": "IDN", "lat":  -8.7450, "lon": 115.2110, "facilities": ["fishing"]},
    "VN SGN": {"un_locode": "VN SGN", "name": "Ho Chi Minh City","country":"VNM","lat":  10.7700, "lon": 106.7000, "facilities": ["container"]},
    "VN DAD": {"un_locode": "VN DAD", "name": "Da Nang",       "country": "VNM", "lat":  16.0700, "lon": 108.2200, "facilities": ["container", "fishing"]},
    "TH BKK": {"un_locode": "TH BKK", "name": "Bangkok",       "country": "THA", "lat":  13.7090, "lon": 100.5790, "facilities": ["container"]},
    "MY KUL": {"un_locode": "MY KUL", "name": "Port Klang",    "country": "MYS", "lat":   3.0000, "lon": 101.4000, "facilities": ["container"]},
    "SG SIN": {"un_locode": "SG SIN", "name": "Singapore",     "country": "SGP", "lat":   1.2655, "lon": 103.8204, "facilities": ["container", "fuel"]},
    "CN SHA": {"un_locode": "CN SHA", "name": "Shanghai",      "country": "CHN", "lat":  31.2304, "lon": 121.4737, "facilities": ["container"]},
    "CN ZOS": {"un_locode": "CN ZOS", "name": "Zhoushan",      "country": "CHN", "lat":  29.9853, "lon": 122.2070, "facilities": ["fishing", "transshipment"]},
    "CN TAO": {"un_locode": "CN TAO", "name": "Qingdao",       "country": "CHN", "lat":  36.0671, "lon": 120.3826, "facilities": ["container", "fishing"]},
    "TW KHH": {"un_locode": "TW KHH", "name": "Kaohsiung",     "country": "TWN", "lat":  22.6273, "lon": 120.3014, "facilities": ["container", "fishing"]},
    "JP TYO": {"un_locode": "JP TYO", "name": "Tokyo",         "country": "JPN", "lat":  35.6500, "lon": 139.7700, "facilities": ["container"]},
    "JP YIZ": {"un_locode": "JP YIZ", "name": "Yaizu",         "country": "JPN", "lat":  34.8650, "lon": 138.3210, "facilities": ["fishing", "transshipment"]},
    "KR PUS": {"un_locode": "KR PUS", "name": "Busan",         "country": "KOR", "lat":  35.1000, "lon": 129.0400, "facilities": ["container", "fishing"]},
    # Indian Ocean / Africa
    "IN BOM": {"un_locode": "IN BOM", "name": "Mumbai",        "country": "IND", "lat":  18.9500, "lon":  72.8400, "facilities": ["container"]},
    "ZA CPT": {"un_locode": "ZA CPT", "name": "Cape Town",     "country": "ZAF", "lat": -33.9100, "lon":  18.4400, "facilities": ["container", "fishing"]},
    "SN DKR": {"un_locode": "SN DKR", "name": "Dakar",         "country": "SEN", "lat":  14.6800, "lon": -17.4250, "facilities": ["fishing", "container"]},
    # Atlantic — Europe / Americas
    "ES VGO": {"un_locode": "ES VGO", "name": "Vigo",          "country": "ESP", "lat":  42.2406, "lon":  -8.7207, "facilities": ["fishing", "transshipment"]},
    "ES CAD": {"un_locode": "ES CAD", "name": "Cádiz",         "country": "ESP", "lat":  36.5298, "lon":  -6.2920, "facilities": ["fishing", "container"]},
    "PT LIS": {"un_locode": "PT LIS", "name": "Lisbon",        "country": "PRT", "lat":  38.7050, "lon":  -9.1450, "facilities": ["container", "fishing"]},
    "FR LRH": {"un_locode": "FR LRH", "name": "La Rochelle",   "country": "FRA", "lat":  46.1500, "lon":  -1.1500, "facilities": ["fishing"]},
    "GB PHD": {"un_locode": "GB PHD", "name": "Peterhead",     "country": "GBR", "lat":  57.5050, "lon":  -1.7800, "facilities": ["fishing"]},
    "NO TOS": {"un_locode": "NO TOS", "name": "Tromsø",        "country": "NOR", "lat":  69.6492, "lon":  18.9553, "facilities": ["fishing"]},
    "IS REK": {"un_locode": "IS REK", "name": "Reykjavik",     "country": "ISL", "lat":  64.1466, "lon": -21.9426, "facilities": ["fishing"]},
    "CA HAL": {"un_locode": "CA HAL", "name": "Halifax",       "country": "CAN", "lat":  44.6488, "lon": -63.5752, "facilities": ["container", "fishing"]},
    "US BOS": {"un_locode": "US BOS", "name": "Boston",        "country": "USA", "lat":  42.3601, "lon": -71.0589, "facilities": ["container", "fishing"]},
    "US MIA": {"un_locode": "US MIA", "name": "Miami",         "country": "USA", "lat":  25.7700, "lon": -80.1700, "facilities": ["container"]},
    "BR REC": {"un_locode": "BR REC", "name": "Recife",        "country": "BRA", "lat":  -8.0570, "lon": -34.8714, "facilities": ["fishing"]},
    "AR MDQ": {"un_locode": "AR MDQ", "name": "Mar del Plata", "country": "ARG", "lat": -38.0323, "lon": -57.5375, "facilities": ["fishing"]},
    # Oceania
    "AU FRE": {"un_locode": "AU FRE", "name": "Fremantle",     "country": "AUS", "lat": -32.0569, "lon": 115.7440, "facilities": ["container", "fishing"]},
    "NZ AKL": {"un_locode": "NZ AKL", "name": "Auckland",      "country": "NZL", "lat": -36.8400, "lon": 174.7700, "facilities": ["container", "fishing"]},
}

_EARTH_RADIUS_MI = 3958.7613


def _haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_MI * math.asin(math.sqrt(a))


def nearest_static_port(lat: float, lon: float) -> dict | None:
    """Return the geographically closest port from the curated _PORTS table.

    Used as the fallback when GFW PORT_VISIT events are unavailable. Returns a
    dict {name, country, un_locode, lat, lon, distance_mi, source: 'static'}
    or None if the table is empty.
    """
    best: dict | None = None
    best_dist = float("inf")
    for port in _PORTS.values():
        d = _haversine_mi(lat, lon, port["lat"], port["lon"])
        if d < best_dist:
            best_dist = d
            best = {
                "name": port["name"],
                "country": port["country"],
                "un_locode": port["un_locode"],
                "lat": port["lat"],
                "lon": port["lon"],
                "distance_mi": round(d, 1),
                "source": "static",
            }
    return best


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
