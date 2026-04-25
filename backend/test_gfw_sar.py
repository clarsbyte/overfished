"""Smoke test for gfw_lookup.get_sar_detections_in_region — verifies the GFW v3
4Wings SAR endpoint contract before wiring it into the supervisor.

Mirrors test_gfw_region.py: surfaces the response body verbatim on HTTP errors
so any contract mismatch (field names, geometry shape, dataset name) is
immediately visible.

Usage:
    python test_gfw_sar.py                              # default: Cebu Strait, 90 days back
    python test_gfw_sar.py <lat> <lon>
    python test_gfw_sar.py <lat> <lon> <radius_mi> <days_back>
    python test_gfw_sar.py <lat> <lon> <radius_mi> 0 <start_date> <end_date>
        e.g. python test_gfw_sar.py 10.0 113.0 100 0 2023-01-01 2024-01-01
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

from gfw_lookup import SAR_DATASET, get_sar_detections_in_region, sar_detection_count
from vessel_lookup import bbox_for_radius

load_dotenv()


def main() -> int:
    if not os.getenv("GFW_API_TOKEN"):
        print("ERROR: GFW_API_TOKEN is not set.")
        return 1

    lat = float(sys.argv[1]) if len(sys.argv) > 1 else 10.2557
    lon = float(sys.argv[2]) if len(sys.argv) > 2 else 123.8966
    radius = float(sys.argv[3]) if len(sys.argv) > 3 else 62.0   # ~100 km
    days_back = int(sys.argv[4]) if len(sys.argv) > 4 else 90

    # Allow explicit date range via argv[5] and argv[6]
    if len(sys.argv) > 6:
        start_d = date.fromisoformat(sys.argv[5])
        end_d = date.fromisoformat(sys.argv[6])
    else:
        end_d = date.today()
        start_d = end_d - timedelta(days=days_back)

    bbox = bbox_for_radius(lat, lon, radius)

    print("SAR query:")
    print(f"  centre        : ({lat}, {lon})")
    print(f"  radius        : {radius} mi (~{radius * 1.609:.0f} km)")
    print(f"  bbox          : lat[{bbox[0]:.4f}, {bbox[2]:.4f}]  lon[{bbox[1]:.4f}, {bbox[3]:.4f}]")
    print(f"  window        : {start_d} -> {end_d}  ({days_back} days)")
    print(f"  dataset       : {SAR_DATASET}")
    print()
    print("Calling gfw_lookup.get_sar_detections_in_region(...)")

    try:
        payload = get_sar_detections_in_region(bbox, start_d.isoformat(), end_d.isoformat())
    except requests.HTTPError as e:
        body = e.response.text if e.response is not None else ""
        status = e.response.status_code if e.response else "?"
        print(f"FAIL: HTTP {status}")
        print(f"      Response body: {body[:2000]}")
        print()
        print("Most likely fix: tweak the body shape in gfw_lookup.get_sar_detections_in_region")
        print("(field names, geometry vs region, dataset name).")
        return 2
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        return 3

    count = sar_detection_count(payload)
    print(f"OK — extracted detection count: {count}")
    print()
    print("Raw 4Wings response (truncated to 4 KB):")
    print(json.dumps(payload, indent=2, default=str)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
