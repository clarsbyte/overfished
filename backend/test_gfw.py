"""Smoke test for the GFW REST client — no LangChain, no LLM.

Usage:
    python test_gfw.py                    # default query
    python test_gfw.py "<mmsi_or_name>"   # custom
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

from dotenv import load_dotenv

from gfw_lookup import (
    get_vessel_events,
    get_vessel_insights,
    pick_best_vessel,
    search_vessel,
)

load_dotenv()


def main() -> int:
    if not os.getenv("GFW_API_TOKEN"):
        print("ERROR: GFW_API_TOKEN is not set. Request one at https://globalfishingwatch.org/our-apis/")
        return 1

    query = sys.argv[1] if len(sys.argv) > 1 else "EVER GIVEN"
    print(f"1) Searching GFW vessels for {query!r} ...")
    try:
        vessels = search_vessel(query)
    except Exception as exc:
        print(f"FAIL search_vessel: {type(exc).__name__}: {exc}")
        return 2
    print(f"   Got {len(vessels)} record(s):")
    for i, r in enumerate(vessels):
        marker = " <- placeholder" if r.mmsi and r.mmsi.startswith("9999") else ""
        print(
            f"     [{i}] name={r.name!r} mmsi={r.mmsi} imo={r.imo} flag={r.flag} "
            f"auths={len(r.authorizations)} owners={len(r.owners)}{marker}"
        )
    if not vessels:
        return 0

    v = pick_best_vessel(vessels, query=query) or vessels[0]
    print(
        f"   Picked: name={v.name!r} mmsi={v.mmsi} imo={v.imo} "
        f"flag={v.flag} vessel_id={v.vessel_id}"
    )
    print(f"   Authorizations on record: {len(v.authorizations)}")
    print(f"   Owners on record: {len(v.owners)}")

    end = date.today()
    start = end - timedelta(days=365)

    print(f"2) Fetching insights for {start} → {end} ...")
    try:
        insights = get_vessel_insights(v.vessel_id, start.isoformat(), end.isoformat())
    except Exception as exc:
        print(f"FAIL insights: {type(exc).__name__}: {exc}")
        return 3

    print("   --- INSIGHTS RESPONSE ---")
    print(json.dumps(insights, indent=2, default=str))
    print("   --- END INSIGHTS ---")

    af = (insights or {}).get("apparentFishing") or {}
    vi = (insights or {}).get("vesselIdentity") or {}
    gap = (insights or {}).get("gap") or {}
    cov = (insights or {}).get("coverage") or {}

    print("   IUU-relevant signals:")
    print(f"     fishing events (period):           "
          f"{(af.get('periodSelectedCounters') or {}).get('events')}")
    print(f"     fishing in no-take MPAs:           "
          f"{len(af.get('eventsInNoTakeMpas') or [])}")
    print(f"     fishing without RFMO authorization:"
          f"{len(af.get('eventsInRfmoWithoutKnownAuthorization') or [])}")
    print(f"     AIS off events (period):           "
          f"{(gap.get('periodSelectedCounters') or {}).get('events')}")
    print(f"     AIS coverage %:                    "
          f"{cov.get('percentage')}")
    print(f"     IUU list match:                    "
          f"{vi.get('iuuVesselList')}")

    print("3) Fetching FISHING events (last 90 days) ...")
    recent_start = (end - timedelta(days=90)).isoformat()
    try:
        events = get_vessel_events(v.vessel_id, "FISHING", recent_start, end.isoformat())
        print(f"   Got {len(events)} fishing event(s).")
    except Exception as exc:
        print(f"FAIL events: {type(exc).__name__}: {exc}")
        return 4

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
