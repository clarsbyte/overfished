"""End-to-end smoke test for the multi-agent vessel-incursion pipeline.

Runs against live APIs (AISStream, GFW, ProtectedSeas) and the supervisor LLM.
Two scenarios:
  1. Port of LA  — AIS-busy, coastal-state cache miss (Pacific US not cached).
  2. Tubbataha   — cached PHL region with PORTLEX populated.

Assertions are structural (sections present + at least one provenance tag),
not exact-text. INSUFFICIENT_DATA outcomes are valid passes.

Usage:
    python test_pipeline.py            # both scenarios
    python test_pipeline.py la         # just Port of LA
    python test_pipeline.py tubbataha  # just Tubbataha
"""

from __future__ import annotations

import os
import sys
import time

from dotenv import load_dotenv

from pipeline_agent import evaluate_incident

load_dotenv()


REQUIRED_SECTIONS = [
    "EVIDENCE OF POTENTIAL IUU FISHING ACTIVITY",
    "INCIDENT LOCATION",
    "AIS STATUS",
    "VESSELS INVESTIGATED",
    "LEGAL CONTEXT",
    "RECOMMENDED ACTIONS",
    "SOURCES",
    "CAVEATS",
]

PROVENANCE_MARKERS = ["last_checked", "FAOLEX", "FISHLEX", "PORTLEX", "ProtectedSeas"]


SCENARIOS = {
    "la": {
        "label": "Port of Los Angeles (AIS-busy, uncached coastal state)",
        "lat": 33.74,
        "lon": -118.26,
        "radius": 30.0,
        "port_country": None,
    },
    "tubbataha": {
        "label": "Tubbataha Reefs (cached PHL region, no-take MPA)",
        "lat": 8.85,
        "lon": 119.917,
        "radius": 30.0,
        "port_country": "PHL",
    },
}


def _check_required_env() -> int:
    missing = [
        k for k in ("ANTHROPIC_API_KEY", "AISSTREAM_API_KEY", "GFW_API_TOKEN")
        if not os.getenv(k)
    ]
    if missing:
        print(f"ERROR: missing env vars: {missing}. Populate .env and retry.")
        return 1
    return 0


def run_scenario(key: str) -> bool:
    s = SCENARIOS[key]
    print()
    print(f"========== {s['label']} ==========")
    print(
        f"Calling evaluate_incident(lat={s['lat']}, lon={s['lon']}, "
        f"radius_miles={s['radius']}, port_country_code={s['port_country']!r})"
    )

    t0 = time.monotonic()
    try:
        output = evaluate_incident(
            s["lat"],
            s["lon"],
            radius_miles=s["radius"],
            port_country_code=s["port_country"],
        )
    except Exception as exc:
        print(f"PIPELINE FAILED: {type(exc).__name__}: {exc}")
        return False
    elapsed = time.monotonic() - t0

    print()
    print("---- evidence document ----")
    print(output)
    print(f"---- end ({elapsed:.1f}s) ----")

    missing_sections = [s for s in REQUIRED_SECTIONS if s not in output]
    found_provenance = [m for m in PROVENANCE_MARKERS if m in output]

    print()
    print(f"Sections missing : {missing_sections or 'none'}")
    print(f"Provenance found : {found_provenance or 'NONE — provenance leak!'}")

    return not missing_sections and bool(found_provenance)


def main() -> int:
    if _check_required_env():
        return 1

    keys = sys.argv[1:] or list(SCENARIOS)
    invalid = [k for k in keys if k not in SCENARIOS]
    if invalid:
        print(f"ERROR: unknown scenario(s) {invalid}; choose from {list(SCENARIOS)}")
        return 2

    results: dict[str, bool] = {}
    for k in keys:
        results[k] = run_scenario(k)

    print()
    print("========== SUMMARY ==========")
    for k, ok in results.items():
        print(f"  {k:12s} {'PASS' if ok else 'FAIL'}")

    return 0 if all(results.values()) else 3


if __name__ == "__main__":
    sys.exit(main())
