"""End-to-end CLI: resolve URLs -> download bytes -> build vessel_cards.json.

This is what the supercomputer (or anyone with the repo) runs once to make
the frontend's vessel-detail panel work without any live API calls per click.

Examples
--------
::

    # Free path: Wikimedia Commons fallback (no API key required)
    python -m overfished_ml.image_enrichment.build_all --use-commons-fallback

    # With MarineTraffic + LLM summaries
    python -m overfished_ml.image_enrichment.build_all --with-summaries

    # Force re-download of every image
    python -m overfished_ml.image_enrichment.build_all --refresh
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .cards import build_vessel_cards
from .download import download_vessel_images
from .enricher import api_key_from_env, enrich_dataset_with_ship_image_urls


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def build_parser() -> argparse.ArgumentParser:
    root = _repo_root()
    default_csv = root / "data" / "local_pipeline" / "gold_vessel_detections_enriched.csv"
    default_cache = root / "data" / "local_pipeline" / "vessel_image_cache.json"
    default_misses = root / "data" / "local_pipeline" / "vessel_image_misses.json"
    default_image_dir = root / "data" / "local_pipeline" / "vessel_images"
    default_dl_errors = root / "data" / "local_pipeline" / "vessel_image_download_errors.json"
    default_cards = root / "data" / "local_pipeline" / "vessel_cards.json"

    parser = argparse.ArgumentParser(
        description="Resolve, download, and assemble vessel image cards in one step."
    )
    parser.add_argument("--input-csv", type=Path, default=default_csv)
    parser.add_argument("--cache-path", type=Path, default=default_cache)
    parser.add_argument("--miss-report-path", type=Path, default=default_misses)
    parser.add_argument("--image-dir", type=Path, default=default_image_dir)
    parser.add_argument("--download-errors-path", type=Path, default=default_dl_errors)
    parser.add_argument("--cards-output", type=Path, default=default_cards)
    parser.add_argument(
        "--public-image-prefix",
        default="/data/vessel_images",
        help="Frontend-relative URL prefix for served images",
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--use-commons-fallback", action="store_true")
    parser.add_argument("--no-commons-fallback", action="store_true")
    parser.add_argument("--with-summaries", action="store_true")
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--max-side", type=int, default=1024)
    parser.add_argument("--quality", type=int, default=85)
    parser.add_argument("--skip-resolve", action="store_true", help="Use existing cache as-is")
    parser.add_argument("--skip-download", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.use_commons_fallback and args.no_commons_fallback:
        raise SystemExit("Cannot pass both --use-commons-fallback and --no-commons-fallback")

    use_commons: bool | None = None
    if args.use_commons_fallback:
        use_commons = True
    elif args.no_commons_fallback:
        use_commons = False

    if not args.skip_resolve:
        resolve_summary = enrich_dataset_with_ship_image_urls(
            input_csv=args.input_csv,
            output_csv=args.input_csv,
            cache_path=args.cache_path,
            miss_report_path=args.miss_report_path,
            api_key=api_key_from_env(),
            base_url=os.getenv("MARINETRAFFIC_BASE_URL", "https://services.marinetraffic.com/api"),
            timeout_seconds=float(os.getenv("MARINETRAFFIC_TIMEOUT_SECONDS", "10")),
            refresh=args.refresh,
            offline=args.offline,
            use_commons_fallback=use_commons,
        )
        print(
            "[1/3] resolve: "
            f"unique_vessels={resolve_summary.unique_vessels}, "
            f"resolved={resolve_summary.resolved_count}, "
            f"misses={resolve_summary.misses}"
        )
    else:
        print("[1/3] resolve: skipped (--skip-resolve)")

    if not args.skip_download:
        dl_summary = download_vessel_images(
            cache_path=args.cache_path,
            image_dir=args.image_dir,
            error_report_path=args.download_errors_path,
            refresh=args.refresh,
            max_workers=args.max_workers,
            max_side=args.max_side,
            quality=args.quality,
        )
        print(
            "[2/3] download: "
            f"requested={dl_summary.requested}, "
            f"downloaded={dl_summary.downloaded}, "
            f"skipped_existing={dl_summary.skipped_existing}, "
            f"failed={dl_summary.failed}"
        )
    else:
        print("[2/3] download: skipped (--skip-download)")

    cards_summary = build_vessel_cards(
        input_csv=args.input_csv,
        cache_path=args.cache_path,
        image_dir=args.image_dir,
        output_path=args.cards_output,
        public_image_prefix=args.public_image_prefix,
        with_summaries=args.with_summaries,
    )
    print(
        "[3/3] cards: "
        f"unique_vessels={cards_summary.unique_vessels}, "
        f"cards={cards_summary.cards_written}, "
        f"with_local_image={cards_summary.with_local_image}, "
        f"with_remote_image={cards_summary.with_remote_image}, "
        f"with_summary={cards_summary.with_summary}, "
        f"output={cards_summary.output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
