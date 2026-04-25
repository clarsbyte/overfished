"""CLI for enriching vessel datasets with MarineTraffic image URLs."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .enricher import api_key_from_env, enrich_dataset_with_ship_image_urls


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def build_parser() -> argparse.ArgumentParser:
    root = _repo_root()
    default_csv = root / "data" / "gold_vessel_detections_enriched.csv"
    parser = argparse.ArgumentParser(description="Enrich vessel CSV with ship_image_url values")
    parser.add_argument("--input-csv", type=Path, default=default_csv)
    parser.add_argument("--output-csv", type=Path, default=default_csv)
    parser.add_argument(
        "--cache-path",
        type=Path,
        default=root / "data" / "local_pipeline" / "vessel_image_cache.json",
    )
    parser.add_argument(
        "--miss-report-path",
        type=Path,
        default=root / "data" / "local_pipeline" / "vessel_image_misses.json",
    )
    parser.add_argument("--refresh", action="store_true", help="Ignore existing cached lookups")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Demo mode: no MarineTraffic or Commons; only overrides, vessel_image_cache.json, and existing CSV URLs",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not call API; only produce miss report")
    parser.add_argument(
        "--override-csv",
        type=Path,
        default=None,
        help="CSV with mmsi,ship_image_url (default: ../data/local_pipeline/ship_image_overrides.csv if present)",
    )
    parser.add_argument(
        "--use-commons-fallback",
        action="store_true",
        help="After MarineTraffic miss, query Wikimedia Commons (free, best-effort)",
    )
    parser.add_argument(
        "--no-commons-fallback",
        action="store_true",
        help="Disable Commons fallback (overrides VESSEL_IMAGE_COMMONS_FALLBACK)",
    )
    parser.add_argument(
        "--commons-delay",
        type=float,
        default=float(os.getenv("VESSEL_IMAGE_COMMONS_DELAY_SECONDS", "0.35")),
        help="Seconds to sleep between Commons requests (politeness)",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    use_commons: bool | None = None
    if args.use_commons_fallback and args.no_commons_fallback:
        raise SystemExit("Cannot pass both --use-commons-fallback and --no-commons-fallback")
    if args.use_commons_fallback:
        use_commons = True
    elif args.no_commons_fallback:
        use_commons = False

    offline = args.offline or os.getenv("VESSEL_IMAGE_OFFLINE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )

    summary = enrich_dataset_with_ship_image_urls(
        input_csv=args.input_csv,
        output_csv=args.output_csv,
        cache_path=args.cache_path,
        miss_report_path=args.miss_report_path,
        api_key=api_key_from_env(),
        base_url=os.getenv("MARINETRAFFIC_BASE_URL", "https://services.marinetraffic.com/api"),
        timeout_seconds=float(os.getenv("MARINETRAFFIC_TIMEOUT_SECONDS", "10")),
        refresh=args.refresh,
        dry_run=args.dry_run,
        offline=offline,
        override_csv_path=args.override_csv,
        use_commons_fallback=use_commons,
        commons_delay_seconds=args.commons_delay,
    )
    mode = "offline" if offline else "online"
    print(
        "Image enrichment complete. "
        f"mode={mode}, "
        f"rows={summary.rows_total}, unique_vessels={summary.unique_vessels}, "
        f"resolved={summary.resolved_count}, overrides={summary.override_hits}, "
        f"cache_hits={summary.cache_hits}, marine_traffic={summary.marine_traffic_hits}, "
        f"commons={summary.commons_hits}, misses={summary.misses}, api_errors={summary.api_errors}, "
        f"output={summary.output_path}, misses_report={summary.miss_report_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
