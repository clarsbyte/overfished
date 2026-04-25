"""Smoke test for classify_vessels_iuu_batch — verifies the threaded batch tool
works AND quantifies the speedup over a sequential baseline.

Bypasses the LangChain supervisor entirely so the threading itself is the
thing under test, not the LLM's tool-calling decisions.

Usage:
    python test_threading.py                          # discover 3 MMSIs from Tubbataha
    python test_threading.py 273435360 <m2> <m3>      # use argv MMSIs verbatim

Exit codes:
    0   parallel run beat sequential by >=40% (typical: 2-3x speedup)
    1   missing API key
    2   structural assertion failed (e.g. missing MMSI block in output)
    3   uncaught exception during run
"""

from __future__ import annotations

import os
import sys
import time
from datetime import date, timedelta

from dotenv import load_dotenv

from gfw_agent import classify_vessel
from gfw_lookup import extract_mmsi, get_events_in_region
from pipeline_agent import classify_vessels_iuu_batch
from vessel_lookup import bbox_for_radius

load_dotenv()

# Tubbataha bbox — used by default-mode MMSI discovery.
DISCOVERY_LAT = 8.85
DISCOVERY_LON = 119.917
DISCOVERY_RADIUS_MI = 50.0
DISCOVERY_DAYS_BACK = 90


def _check_required_env() -> int:
    missing = [k for k in ("ANTHROPIC_API_KEY", "GFW_API_TOKEN") if not os.getenv(k)]
    if missing:
        print(f"ERROR: missing env vars: {', '.join(missing)}")
        return 1
    return 0


def _discover_mmsis(n: int = 3) -> list[str]:
    """Pull recent unique MMSIs from GFW FISHING events around Tubbataha."""
    end_d = date.today()
    start_d = end_d - timedelta(days=DISCOVERY_DAYS_BACK)
    bbox = bbox_for_radius(DISCOVERY_LAT, DISCOVERY_LON, DISCOVERY_RADIUS_MI)
    events = get_events_in_region(
        bbox,
        event_type="FISHING",
        start_date=start_d.isoformat(),
        end_date=end_d.isoformat(),
        limit=100,
    )
    seen: list[str] = []
    for e in events:
        mmsi = extract_mmsi(e)
        if mmsi and mmsi not in seen:
            seen.append(mmsi)
        if len(seen) >= n:
            break
    return seen


def main() -> int:
    code = _check_required_env()
    if code != 0:
        return code

    if len(sys.argv) > 1:
        mmsis = [arg.strip() for arg in sys.argv[1:] if arg.strip()][:6]
        print(f"Using {len(mmsis)} argv-supplied MMSIs: {mmsis}")
    else:
        print("Discovering MMSIs from Tubbataha FISHING events (last 90 d)...")
        try:
            mmsis = _discover_mmsis(3)
        except Exception as exc:
            print(f"FAIL: MMSI discovery error: {type(exc).__name__}: {exc}")
            return 3
        if not mmsis:
            print("FAIL: no MMSIs discovered. Try passing them as args.")
            return 3
        print(f"Discovered MMSIs: {mmsis}")

    print()
    print("=" * 70)
    print("STAGE 1 — sequential baseline (loop over classify_vessel)")
    print("=" * 70)
    seq_start = time.perf_counter()
    seq_results: list[tuple[str, str]] = []
    try:
        for m in mmsis:
            t0 = time.perf_counter()
            verdict = classify_vessel(m)
            dt = time.perf_counter() - t0
            print(f"  MMSI {m}: classified in {dt:5.1f}s  ({len(verdict)} chars)")
            seq_results.append((m, verdict))
    except Exception as exc:
        print(f"FAIL: sequential run raised {type(exc).__name__}: {exc}")
        return 3
    seq_elapsed = time.perf_counter() - seq_start
    print(f"Sequential total: {seq_elapsed:.1f}s")

    print()
    print("=" * 70)
    print("STAGE 2 — parallel via classify_vessels_iuu_batch (ThreadPoolExecutor)")
    print("=" * 70)
    par_start = time.perf_counter()
    try:
        par_output = classify_vessels_iuu_batch.invoke({"mmsis": mmsis})
    except Exception as exc:
        print(f"FAIL: parallel run raised {type(exc).__name__}: {exc}")
        return 3
    par_elapsed = time.perf_counter() - par_start
    print(f"Parallel total:   {par_elapsed:.1f}s")
    print()
    print(f"Parallel output ({len(par_output)} chars), preview:")
    print(par_output[:1500])
    print("..." if len(par_output) > 1500 else "")

    print()
    print("=" * 70)
    print("STAGE 3 — assertions")
    print("=" * 70)

    failures: list[str] = []
    for m in mmsis:
        if f"=== MMSI {m} ===" not in par_output:
            failures.append(f"missing block for MMSI {m}")
    if "FAILED" in par_output:
        failures.append("at least one MMSI returned a FAILED block")

    speedup = seq_elapsed / par_elapsed if par_elapsed > 0 else 0.0
    print(f"  Sequential : {seq_elapsed:6.1f}s")
    print(f"  Parallel   : {par_elapsed:6.1f}s")
    print(f"  Speedup    : {speedup:5.2f}x")
    print(f"  Threshold  : parallel must be < sequential * 0.6")
    print()

    if speedup < (1 / 0.6):
        failures.append(
            f"speedup {speedup:.2f}x below threshold (parallel {par_elapsed:.1f}s "
            f"vs sequential {seq_elapsed:.1f}s)"
        )

    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 2

    print("OK — threading verified, structural assertions passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
