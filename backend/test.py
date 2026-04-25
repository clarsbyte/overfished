"""Smoke test for the AISStream lookup layer — no LangChain, no LLM.

Usage:
    python test.py                       # defaults to Port of Los Angeles, 50 mi, 30 s
    python test.py <lat> <lon>           # custom point
    python test.py <lat> <lon> <radius>  # custom radius (miles)
    python test.py <lat> <lon> <radius> <listen_seconds>
"""

from __future__ import annotations

import os
import sys
import time

from dotenv import load_dotenv

from vessel_lookup import bbox_for_radius, vessels_within_radius

load_dotenv()


def main() -> int:
    if not os.getenv("AISSTREAM_API_KEY"):
        print("ERROR: AISSTREAM_API_KEY is not set. Copy .env.example to .env and fill it in.")
        return 1

    # Default: Port of Los Angeles — busy, plenty of AIS traffic.
    lat = float(sys.argv[1]) if len(sys.argv) > 1 else 33.74
    lon = float(sys.argv[2]) if len(sys.argv) > 2 else -118.26
    radius = float(sys.argv[3]) if len(sys.argv) > 3 else 50.0
    listen = float(sys.argv[4]) if len(sys.argv) > 4 else 30.0

    bbox = bbox_for_radius(lat, lon, radius)
    print(f"Query point:     ({lat}, {lon})")
    print(f"Radius:          {radius} mi")
    print(f"Listen window:   {listen} s")
    print(f"Bounding box:    lat [{bbox[0]:.4f}, {bbox[2]:.4f}], lon [{bbox[1]:.4f}, {bbox[3]:.4f}]")
    print("Connecting to wss://stream.aisstream.io/v0/stream ...")

    t0 = time.monotonic()
    try:
        vessels = vessels_within_radius(lat, lon, radius, listen)
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 2
    elapsed = time.monotonic() - t0

    print(f"Done in {elapsed:.1f}s. {len(vessels)} vessel(s) within {radius} mi.")
    for v in vessels[:20]:
        print(v.as_line())
    if len(vessels) > 20:
        print(f"... and {len(vessels) - 20} more")

    return 0 if vessels or elapsed >= listen * 0.9 else 3


if __name__ == "__main__":
    sys.exit(main())
