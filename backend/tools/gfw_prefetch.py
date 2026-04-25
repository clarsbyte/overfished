"""Pre-fetch real vessel tracks from GFW into a local cache.

Run this once (or whenever you want fresh data) before the demo:

    cd backend
    .venv/bin/python -m tools.gfw_prefetch

Behavior:

  * Reads ``backend/fixtures/fishery_regions.json`` for the IUU hotspot polygons.
  * For each region, asks GFW's 4Wings API for vessel-presence rows over a
    24h window (defaults to ``[now-6d, now-5d]`` because GFW lags ~96h).
  * Per region, picks up to N vessels weighted by the region's risk class.
  * Sorts each vessel's rows by timestamp → polyline of [[lat,lng], ...].
  * Writes ``fixtures/vessel_tracks_global.json`` (overwriting) and a
    sibling ``fixtures/gfw_metadata.json`` with the fetch metadata.

Idempotent. Safe to re-run. Fails loudly if the token is missing or the API
errors; the runtime always has a procedural fallback in
``vessel_tracks_global.fallback.json`` so the demo never breaks.

Important: GFW caps the same API token at 1 concurrent report. We serialize
strictly — one region at a time.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Make this runnable as `python -m tools.gfw_prefetch` from the backend/ dir,
# and also from a fully-qualified entrypoint.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.gfw_client import GFWClient, GFWError  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
REGIONS_FIXTURE = FIXTURES_DIR / "fishery_regions.json"
OUT_TRACKS = FIXTURES_DIR / "vessel_tracks_global.json"
OUT_META = FIXTURES_DIR / "gfw_metadata.json"

# Per-region budget by risk class (vessels to keep). Higher-risk regions get
# more representation in the global fleet; safe regions still get a couple
# so the world doesn't look empty.
RISK_BUDGET: dict[str, int] = {
    "confirmed_iuu": 12,
    "high_risk": 6,
    "suspect": 3,
    "safe": 2,
}

DEFAULT_TARGET_FLEET_SIZE = 40  # halved from 80 — perf budget for the globe
MIN_TRACK_POINTS = 3  # vessels with fewer hourly positions are skipped

# Tokens whose JWT `data.name` field appears in this set are refused — they
# correspond to credentials that leaked into the chat transcript and need to
# be treated as compromised regardless of whether they were rotated.
LEAKED_TOKEN_NAMES: frozenset[str] = frozenset({"Overfished"})


def _flatten_report(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the dataset-keyed entries[].dataset[]. response into flat rows."""
    out: list[dict[str, Any]] = []
    for entry in payload.get("entries", []) or []:
        for _dataset_key, rows in entry.items():
            if isinstance(rows, list):
                out.extend(rows)
    return out


def _classify_track_points(rows: list[dict[str, Any]]) -> list[list[float]]:
    """Sort by date and return [[lat, lng], ...]. Caller filters short tracks."""
    rows = [r for r in rows if r.get("lat") is not None and r.get("lon") is not None]
    rows.sort(key=lambda r: str(r.get("date", "")))
    return [[float(r["lat"]), float(r["lon"])] for r in rows]


def _vessel_record(rows: list[dict[str, Any]], risk: str) -> dict[str, Any] | None:
    """Build a fleet entry from one vessel's hourly rows."""
    pts = _classify_track_points(rows)
    if len(pts) < MIN_TRACK_POINTS:
        return None
    head = next((r for r in rows if r.get("shipName") or r.get("mmsi")), rows[0])
    mmsi = head.get("mmsi") or ""
    name = (head.get("shipName") or mmsi or "UNNAMED").strip() or "UNNAMED"
    flag = (head.get("flag") or "").strip()
    return {
        "mmsi": str(mmsi) if mmsi else (head.get("vesselId", "") or "")[:9],
        "name": name,
        "flag": flag,
        "risk": risk,
        "points": pts,
    }


def _group_by_vessel(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        key = r.get("vesselId") or r.get("vessel_id") or r.get("mmsi")
        if not key:
            continue
        grouped.setdefault(str(key), []).append(r)
    return grouped


async def _fetch_region(
    client: GFWClient, region: dict[str, Any], start: str, end: str
) -> tuple[list[dict[str, Any]], int]:
    """Run one report request for a region; return (vessel records, request count)."""
    risk = region.get("risk", "suspect")
    budget = RISK_BUDGET.get(risk, 4)
    polygon = region["geometry"]
    label = region.get("region_id", "<unknown>")

    request_count = 1  # one POST /4wings/report per region; recovery polls would add more
    try:
        payload = await client.vessel_presence_report(polygon, start, end)
    except GFWError as e:
        print(f"  ! {label:<25} skipped: {e}")
        return ([], request_count)

    rows = _flatten_report(payload)
    grouped = _group_by_vessel(rows)
    vessels: list[dict[str, Any]] = []
    for _key, vrows in grouped.items():
        rec = _vessel_record(vrows, risk)
        if rec is not None:
            vessels.append(rec)
        if len(vessels) >= budget:
            break

    print(f"  ✓ {label:<25} +{len(vessels):>3} vessels  (rows={len(rows)})")
    return (vessels, request_count)


def _resolve_window(days_ago: int) -> tuple[str, str]:
    """Return (start, end) ISO date strings for a 24h window N days back."""
    end_d = date.today() - timedelta(days=days_ago)
    start_d = end_d - timedelta(days=1)
    return start_d.isoformat(), end_d.isoformat()


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode the JSON payload of a JWT. No signature check — used only to
    inspect the embedded ``data.name`` field for the leaked-token guard.
    """
    import base64

    try:
        _, payload_b64, _ = token.split(".")
        # JWT base64 is URL-safe, no padding; pad to a multiple of 4 first.
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        return {}


def _guard_against_leaked_token() -> None:
    """Refuse to run if the configured token matches a known-leaked credential."""
    token = os.environ.get("GFW_API_ACCESS_TOKEN", "")
    if not token:
        return  # GFWClient will surface a clearer error
    payload = _decode_jwt_payload(token)
    name = payload.get("data", {}).get("name", "")
    if name in LEAKED_TOKEN_NAMES:
        raise GFWError(
            f"Refusing to use leaked token (data.name='{name}'). This token "
            "appeared in chat history and must be treated as compromised. "
            "Rotate it at https://globalfishingwatch.org/our-apis/tokens "
            "and update GFW_API_ACCESS_TOKEN in backend/.env."
        )


async def prefetch(target_fleet_size: int = DEFAULT_TARGET_FLEET_SIZE) -> dict[str, Any]:
    """Main orchestrator. Returns the metadata that's written to disk."""
    _guard_against_leaked_token()

    days_ago = int(os.environ.get("GFW_PREFETCH_DAYS_AGO", "5"))
    start, end = _resolve_window(days_ago)
    print(f"GFW prefetch: window {start} → {end}  (target ≈ {target_fleet_size} vessels)\n")

    regions = json.loads(REGIONS_FIXTURE.read_text())
    # Order: high-risk regions first so we exhaust budget there.
    risk_order = {"confirmed_iuu": 0, "high_risk": 1, "suspect": 2, "safe": 3}
    regions.sort(key=lambda r: risk_order.get(r.get("risk", "suspect"), 9))

    fleet: dict[str, dict[str, Any]] = {}  # vessel_id → record
    regions_covered: list[str] = []
    api_request_count = 0

    async with GFWClient() as client:
        for region in regions:
            if len(fleet) >= target_fleet_size:
                print(f"  · target fleet size reached ({len(fleet)}); skipping rest")
                break
            records, n_requests = await _fetch_region(client, region, start, end)
            api_request_count += n_requests
            for rec in records:
                # De-dup by mmsi (vessels can fish in multiple regions in 24h)
                key = rec["mmsi"] or f"{rec['name']}-{rec['flag']}"
                if key in fleet:
                    continue
                fleet[key] = rec
            if records:
                regions_covered.append(region["region_id"])

    out = list(fleet.values())[:target_fleet_size]
    OUT_TRACKS.write_text(json.dumps(out, indent=2))

    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "date_range": {"start": start, "end": end},
        "days_ago": days_ago,
        "regions_covered": regions_covered,
        "vessel_count": len(out),
        "total_position_points": sum(len(v["points"]) for v in out),
        "api_requests_this_run": api_request_count,
        "rate_limit_reminder": "GFW caps non-commercial use at 50,000 requests/day, 1.55M/month.",
        "source": "GFW v3 4Wings AIS Vessel Presence",
    }
    OUT_META.write_text(json.dumps(meta, indent=2))

    print(
        f"\n✅ Wrote {len(out)} vessels with real GFW data to "
        f"{OUT_TRACKS.relative_to(FIXTURES_DIR.parent)}\n"
        f"   ({meta['total_position_points']} total position points; "
        f"{api_request_count} API requests this run, well under the 50K/day cap)"
    )
    return meta


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "-n",
        "--fleet-size",
        type=int,
        default=DEFAULT_TARGET_FLEET_SIZE,
        help=f"Target number of vessels in the fleet (default {DEFAULT_TARGET_FLEET_SIZE})",
    )
    args = parser.parse_args()
    try:
        # Load .env if python-dotenv is available; otherwise rely on shell env.
        try:
            from dotenv import load_dotenv  # type: ignore[import-not-found]

            load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        except ImportError:
            pass
        asyncio.run(prefetch(target_fleet_size=args.fleet_size))
    except GFWError as e:
        print(f"\n❌ GFW prefetch failed: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    _cli()
