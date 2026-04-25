"""Smoke test for gfw_lookup.get_events_in_region — verifies the GFW v3
region-bbox events endpoint before running the full pipeline.

Does NOT use LangChain or the LLM. Just hits the API, prints the response,
and surfaces the response body verbatim on HTTP errors so contract mismatches
(field names, polygon shape, etc.) are immediately visible.

Usage:
    python test_gfw_region.py                     # default: Tubbataha 50 mi, 90 days
    python test_gfw_region.py <lat> <lon>         # custom centre
    python test_gfw_region.py <lat> <lon> <radius_mi> <days_back>
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

from gfw_lookup import EVENT_DATASETS, extract_mmsi, get_events_in_region
from vessel_lookup import bbox_for_radius

load_dotenv()


def main() -> int:
    if not os.getenv("GFW_API_TOKEN"):
        print("ERROR: GFW_API_TOKEN is not set.")
        return 1

    lat = float(sys.argv[1]) if len(sys.argv) > 1 else 8.85
    lon = float(sys.argv[2]) if len(sys.argv) > 2 else 119.917
    radius = float(sys.argv[3]) if len(sys.argv) > 3 else 50.0
    days_back = int(sys.argv[4]) if len(sys.argv) > 4 else 90

    end_d = date.today()
    start_d = end_d - timedelta(days=days_back)
    bbox = bbox_for_radius(lat, lon, radius)

    print("Region query:")
    print(f"  centre        : ({lat}, {lon})")
    print(f"  radius        : {radius} mi")
    print(f"  bbox          : lat[{bbox[0]:.4f}, {bbox[2]:.4f}]  lon[{bbox[1]:.4f}, {bbox[3]:.4f}]")
    print(f"  window        : {start_d} → {end_d}  ({days_back} days)")
    print(f"  event_type    : FISHING")
    print(f"  dataset       : {EVENT_DATASETS['FISHING']}")
    print()
    print("Calling gfw_lookup.get_events_in_region(...)")

    try:
        events = get_events_in_region(
            bbox,
            event_type="FISHING",
            start_date=start_d.isoformat(),
            end_date=end_d.isoformat(),
            limit=100,
        )
    except requests.HTTPError as e:
        body = ""
        if e.response is not None:
            body = e.response.text
        print(f"FAIL: HTTP {e.response.status_code if e.response else '?'}")
        print(f"      Response body: {body[:2000]}")
        print()
        print("Most likely fix: tweak the body shape in gfw_lookup.get_events_in_region")
        print("(field names, region.geojson nesting, datasets[] vs dataset).")
        return 2
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        return 3

    print(f"OK — {len(events)} event(s) returned.")
    print()

    if not events:
        print("Note: empty result is legitimate if the bbox/window has no fishing events.")
        print("Try: python test_gfw_region.py 8.85 119.917 200 365")
        return 0

    by_mmsi: dict[str, dict] = {}
    skipped_no_mmsi = 0
    for e in events:
        mmsi = extract_mmsi(e)
        if not mmsi:
            skipped_no_mmsi += 1
            continue
        prev = by_mmsi.get(mmsi)
        if prev is None or (e.get("end") or "") > (prev.get("end") or ""):
            by_mmsi[mmsi] = e

    print(f"Unique MMSIs : {len(by_mmsi)}")
    print(f"Events without MMSI: {skipped_no_mmsi}")
    print()

    print("First 5 unique vessels (sorted by most-recent event end):")
    ranked = sorted(by_mmsi.items(), key=lambda kv: kv[1].get("end") or "", reverse=True)[:5]
    for mmsi, e in ranked:
        vessel = e.get("vessel") or {}
        pos = e.get("position") or {}
        print(
            f"  MMSI={mmsi}  name={vessel.get('name', '?')!r}  flag={vessel.get('flag', '?')}"
            f"  end={e.get('end', '?')}  pos=({pos.get('lat')}, {pos.get('lon')})"
        )

    print()
    print("Sample raw event (first):")
    print(json.dumps(events[0], indent=2, default=str)[:2000])

    return 0


if __name__ == "__main__":
    sys.exit(main())
