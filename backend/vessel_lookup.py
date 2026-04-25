"""AISStream.io lookup helpers used by the LangChain tool.

AISStream is a WebSocket feed, not a request/response API. To answer
"are there vessels near (lat, lon)?" we connect, subscribe to a bounding
box, listen for a fixed window, dedupe by MMSI, and filter by haversine
distance to the true radius.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
from dataclasses import dataclass, field
from typing import Any

import websockets

EARTH_RADIUS_MI = 3958.7613
DEG_LAT_MI = 69.0

AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"
DEFAULT_LISTEN_SECONDS = 30.0

SHIP_TYPE_RANGES: list[tuple[range, str]] = [
    (range(20, 30), "WIG"),
    (range(30, 31), "Fishing"),
    (range(31, 33), "Towing"),
    (range(33, 34), "Dredging"),
    (range(34, 35), "Diving"),
    (range(35, 36), "Military"),
    (range(36, 37), "Sailing"),
    (range(37, 38), "Pleasure craft"),
    (range(40, 50), "High-speed craft"),
    (range(50, 60), "Special"),
    (range(60, 70), "Passenger"),
    (range(70, 80), "Cargo"),
    (range(80, 90), "Tanker"),
    (range(90, 100), "Other"),
]


@dataclass
class Vessel:
    name: str
    mmsi: str | None
    type: str | None
    latitude: float
    longitude: float
    distance_miles: float

    def as_line(self) -> str:
        bits = [self.name]
        if self.mmsi:
            bits.append(f"MMSI {self.mmsi}")
        if self.type:
            bits.append(self.type)
        loc = f"({self.latitude:.4f}, {self.longitude:.4f})"
        return f"- {' | '.join(bits)} at {loc} — {self.distance_miles:.1f} mi"


@dataclass
class _Observation:
    mmsi: str
    latitude: float | None = None
    longitude: float | None = None
    name: str | None = None
    type_code: int | None = None
    extras: dict[str, Any] = field(default_factory=dict)


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(a))


def bbox_for_radius(lat: float, lon: float, radius_mi: float) -> tuple[float, float, float, float]:
    dlat = radius_mi / DEG_LAT_MI
    cos_lat = max(math.cos(math.radians(lat)), 0.01)
    dlon = radius_mi / (DEG_LAT_MI * cos_lat)
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)


def label_ship_type(code: int | None) -> str | None:
    if code is None:
        return None
    for rng, label in SHIP_TYPE_RANGES:
        if code in rng:
            return label
    return f"Type {code}"


def _clean_name(raw: Any) -> str | None:
    if raw is None:
        return None
    name = str(raw).replace("@", "").strip()
    return name or None


async def _stream_vessels(
    bbox: tuple[float, float, float, float],
    listen_seconds: float,
    api_key: str,
) -> list[_Observation]:
    lat_min, lon_min, lat_max, lon_max = bbox
    subscription = {
        "APIKey": api_key,
        "BoundingBoxes": [[[lat_min, lon_min], [lat_max, lon_max]]],
        "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
    }

    seen: dict[str, _Observation] = {}
    loop = asyncio.get_event_loop()
    deadline = loop.time() + listen_seconds

    async with websockets.connect(AISSTREAM_URL, ping_interval=20) as ws:
        await ws.send(json.dumps(subscription))
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if "error" in msg:
                raise RuntimeError(f"AISStream error: {msg['error']}")

            meta = msg.get("MetaData") or {}
            mmsi = meta.get("MMSI")
            if mmsi is None:
                continue
            mmsi_key = str(mmsi)
            obs = seen.setdefault(mmsi_key, _Observation(mmsi=mmsi_key))

            lat = meta.get("latitude")
            lon = meta.get("longitude")
            if lat is not None and lon is not None:
                obs.latitude = float(lat)
                obs.longitude = float(lon)

            name = _clean_name(meta.get("ShipName"))
            if name:
                obs.name = name

            payload = msg.get("Message") or {}
            static = payload.get("ShipStaticData")
            if isinstance(static, dict):
                obs.type_code = static.get("Type", obs.type_code)
                static_name = _clean_name(static.get("Name"))
                if static_name and not obs.name:
                    obs.name = static_name

    return list(seen.values())


def fetch_vessels_in_bbox(
    bbox: tuple[float, float, float, float],
    listen_seconds: float = DEFAULT_LISTEN_SECONDS,
) -> list[_Observation]:
    api_key = os.getenv("AISSTREAM_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "AISSTREAM_API_KEY is not set. Register a free key at "
            "https://aisstream.io and add it to your .env file."
        )
    return asyncio.run(_stream_vessels(bbox, listen_seconds, api_key))


def vessels_within_radius(
    latitude: float,
    longitude: float,
    radius_miles: float,
    listen_seconds: float = DEFAULT_LISTEN_SECONDS,
) -> list[Vessel]:
    bbox = bbox_for_radius(latitude, longitude, radius_miles)
    observations = fetch_vessels_in_bbox(bbox, listen_seconds)
    found: list[Vessel] = []
    for obs in observations:
        if obs.latitude is None or obs.longitude is None:
            continue
        dist = haversine_miles(latitude, longitude, obs.latitude, obs.longitude)
        if dist > radius_miles:
            continue
        found.append(
            Vessel(
                name=obs.name or "Unknown",
                mmsi=obs.mmsi,
                type=label_ship_type(obs.type_code),
                latitude=obs.latitude,
                longitude=obs.longitude,
                distance_miles=dist,
            )
        )
    found.sort(key=lambda v: v.distance_miles)
    return found
