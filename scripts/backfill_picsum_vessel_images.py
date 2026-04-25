#!/usr/bin/env python3
"""Merge Picsum placeholder URLs into ``vessel_image_cache.json`` for offline JPG pulls.

Illustrative hackathon images only (not real vessel photos). Stable per MMSI via
Picsum's ``/seed/{seed}/w/h`` URL scheme.

After this script::

    # From repo root, with ml installed (``pip install -e ./ml``) and requests/Pillow deps.
    python -m overfished_ml.image_enrichment.build_all --skip-resolve

That runs ``download_vessel_images`` then ``build_vessel_cards`` so each MMSI
gets ``image_path`` under ``data/local_pipeline/vessel_images/`` when the
download succeeds, and ``vessel_cards.json`` picks up local paths.

Or invoke the two steps from Python::

    from pathlib import Path
    from overfished_ml.image_enrichment.download import download_vessel_images
    from overfished_ml.image_enrichment.cards import build_vessel_cards

    root = Path(__file__).resolve().parents[1]
    lp = root / "data" / "local_pipeline"
    download_vessel_images(
        cache_path=lp / "vessel_image_cache.json",
        image_dir=lp / "vessel_images",
        error_report_path=lp / "vessel_image_download_errors.json",
    )
    build_vessel_cards(
        input_csv=lp / "gold_vessel_detections_enriched.csv",
        cache_path=lp / "vessel_image_cache.json",
        image_dir=lp / "vessel_images",
        output_path=lp / "vessel_cards.json",
    )
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import quote


def _picsum_url(mmsi: str, width: int, height: int) -> str:
    seed = quote(f"vessel-{mmsi}", safe="")
    return f"https://picsum.photos/seed/{seed}/{width}/{height}"


def _load_json_list(path: Path) -> list:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, list) else []


def _load_json_dict(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _mmsi_from_tracks(tracks: list) -> set[str]:
    out: set[str] = set()
    for row in tracks:
        if not isinstance(row, dict):
            continue
        m = row.get("mmsi")
        if m is not None and str(m).strip():
            out.add(str(m).strip())
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Add Picsum URLs to vessel_image_cache.json for missing MMSIs.")
    root = Path(__file__).resolve().parents[1]
    lp = root / "data" / "local_pipeline"
    parser.add_argument("--cards", type=Path, default=lp / "vessel_cards.json", help="JSON object keyed by MMSI")
    parser.add_argument(
        "--tracks",
        type=Path,
        default=root / "backend" / "fixtures" / "vessel_tracks_global.fallback.json",
        help="Global tracks JSON array (optional; union MMSIs into allowlist)",
    )
    parser.add_argument("--cache", type=Path, default=lp / "vessel_image_cache.json")
    parser.add_argument("--width", type=int, default=800)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    mmsi_set: set[str] = set()
    if args.cards.exists():
        cards = _load_json_dict(args.cards)
        mmsi_set |= {str(k).strip() for k in cards if str(k).strip()}
    if args.tracks.exists():
        mmsi_set |= _mmsi_from_tracks(_load_json_list(args.tracks))

    if not mmsi_set:
        print("No MMSI keys found; check --cards and --tracks paths.")
        return 1

    cache: dict[str, str] = {}
    if args.cache.exists():
        parsed = _load_json_dict(args.cache)
        cache = {str(k).strip(): str(v).strip() for k, v in parsed.items() if str(v).strip()}

    added = 0
    for mmsi in sorted(mmsi_set):
        if mmsi in cache and cache[mmsi].startswith("http"):
            continue
        cache[mmsi] = _picsum_url(mmsi, args.width, args.height)
        added += 1

    print(f"MMSI in union: {len(mmsi_set)}, cache entries now: {len(cache)}, new Picsum URLs added: {added}")

    if args.dry_run:
        print("Dry run; not writing cache.")
        return 0

    args.cache.parent.mkdir(parents=True, exist_ok=True)
    args.cache.write_text(json.dumps(dict(sorted(cache.items())), indent=2), encoding="utf-8")
    print(f"Wrote {args.cache}")
    print("Next: python -m overfished_ml.image_enrichment.build_all --skip-resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
