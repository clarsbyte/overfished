"""Assign random aerial ship crops from a local dataset to MMSIs and build cards.

Use the ``ships-aerial-images`` tree produced by unzipping ``archive.zip`` into
``data/datasets/ships-aerial-images/`` (repo root). On ASUS GX10, typical flow::

    unzip -q -o path/to/archive.zip -d data/datasets
    # yields data/datasets/ships-aerial-images/{train,valid,test}/images/*.jpg

    # Optional: rsync the zip or extracted tree first, e.g.
    #   GX10_SYNC_EXTRA=archive.zip overfished-gx10 sync

    overfished-assign-aerial --aerial-root data/datasets/ships-aerial-images

See ``overfished_ml.local_pipeline.remote.pull_gx10_artifacts`` defaults to pull
``vessel_images/`` and ``vessel_cards.json`` back to your laptop.
"""

from __future__ import annotations

import argparse
import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from PIL import Image, UnidentifiedImageError

from .cards import build_vessel_cards
from .download import _resize_to_max, _save_jpeg


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_aerial_dataset_root() -> Path:
    return _repo_root() / "data" / "datasets" / "ships-aerial-images"


def discover_aerial_jpgs(aerial_root: Path) -> list[Path]:
    """Collect ``*.jpg`` under any ``.../images/`` directory below ``aerial_root``."""
    if not aerial_root.is_dir():
        return []
    found: list[Path] = []
    for images_dir in aerial_root.rglob("images"):
        if not images_dir.is_dir():
            continue
        found.extend(p for p in images_dir.glob("*.jpg") if p.is_file())
    return sorted(found)


def unique_sorted_mmsi_from_csv(csv_path: Path) -> list[str]:
    frame = pd.read_csv(csv_path)
    if "mmsi" not in frame.columns:
        raise ValueError("Input CSV must include an `mmsi` column")
    raw = frame["mmsi"].dropna().astype(str).str.strip()
    raw = raw[raw != ""]
    return sorted({m for m in raw.unique()})


def _pair_mmsi_to_sources(
    mmsi_list: list[str],
    pool: list[Path],
    rng: random.Random,
) -> list[tuple[str, Path]]:
    """Deterministic MMSI order; shuffled pool; assign without replacement, reshuffle when exhausted."""
    if not pool:
        raise ValueError("No JPEG images found under aerial-root (expected .../images/*.jpg)")
    work = pool.copy()
    rng.shuffle(work)
    idx = 0
    out: list[tuple[str, Path]] = []
    for mmsi in mmsi_list:
        if idx >= len(work):
            work = pool.copy()
            rng.shuffle(work)
            idx = 0
        out.append((mmsi, work[idx]))
        idx += 1
    return out


def _write_one_jpeg(
    mmsi: str,
    src: Path,
    dest: Path,
    *,
    max_side: int,
    quality: int,
) -> tuple[str, str | None]:
    try:
        with Image.open(src) as im:
            im = _resize_to_max(im, max_side)
            _save_jpeg(im, dest, quality=quality)
        return (mmsi, None)
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        return (mmsi, str(exc))


def strip_cache_entries_for_mmsi(cache_path: Path, mmsi_keys: set[str]) -> int:
    """Remove URL entries for given MMSIs so cards do not carry misleading ``image_source_url``."""
    if not cache_path.exists() or not mmsi_keys:
        return 0
    try:
        parsed: Any = json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    if not isinstance(parsed, dict):
        return 0
    removed = 0
    for k in list(parsed.keys()):
        if str(k).strip() in mmsi_keys:
            del parsed[k]
            removed += 1
    if removed:
        cache_path.write_text(json.dumps(parsed, indent=2, sort_keys=True), encoding="utf-8")
    return removed


@dataclass(frozen=True)
class AerialAssignSummary:
    mmsi_count: int
    pool_size: int
    written: int
    failed: int
    cache_entries_removed: int
    cards_output: str


def assign_aerial_images_to_mmsi(
    *,
    input_csv: Path,
    aerial_root: Path,
    image_dir: Path,
    cache_path: Path,
    cards_output: Path,
    seed: int,
    max_workers: int,
    max_side: int,
    quality: int,
    clean_first: bool,
    public_image_prefix: str,
    with_summaries: bool = False,
) -> AerialAssignSummary:
    mmsi_list = unique_sorted_mmsi_from_csv(input_csv)
    pool = discover_aerial_jpgs(aerial_root)
    rng = random.Random(seed)
    pairs = _pair_mmsi_to_sources(mmsi_list, pool, rng)
    mmsi_set = {m for m, _ in pairs}

    image_dir.mkdir(parents=True, exist_ok=True)
    if clean_first:
        for mmsi in mmsi_set:
            p = image_dir / f"{mmsi}.jpg"
            if p.is_file():
                p.unlink()

    written = 0
    failed = 0
    if max_workers <= 1:
        for mmsi, src in pairs:
            dest = image_dir / f"{mmsi}.jpg"
            _, err = _write_one_jpeg(mmsi, src, dest, max_side=max_side, quality=quality)
            if err is None:
                written += 1
            else:
                failed += 1
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {
                ex.submit(
                    _write_one_jpeg,
                    mmsi,
                    src,
                    image_dir / f"{mmsi}.jpg",
                    max_side=max_side,
                    quality=quality,
                ): mmsi
                for mmsi, src in pairs
            }
            for fut in as_completed(futs):
                _, err = fut.result()
                if err is None:
                    written += 1
                else:
                    failed += 1

    removed = strip_cache_entries_for_mmsi(cache_path, mmsi_set)
    build_vessel_cards(
        input_csv=input_csv,
        cache_path=cache_path,
        image_dir=image_dir,
        output_path=cards_output,
        public_image_prefix=public_image_prefix,
        with_summaries=with_summaries,
    )
    return AerialAssignSummary(
        mmsi_count=len(mmsi_list),
        pool_size=len(pool),
        written=written,
        failed=failed,
        cache_entries_removed=removed,
        cards_output=str(cards_output),
    )


def build_parser() -> argparse.ArgumentParser:
    root = _repo_root()
    default_csv = root / "data" / "local_pipeline" / "gold_vessel_detections_enriched.csv"
    default_cache = root / "data" / "local_pipeline" / "vessel_image_cache.json"
    default_image_dir = root / "data" / "local_pipeline" / "vessel_images"
    default_cards = root / "data" / "local_pipeline" / "vessel_cards.json"

    p = argparse.ArgumentParser(
        description=(
            "Map each unique MMSI in the gold CSV to a random aerial ship JPEG from a "
            "local dataset, write data/local_pipeline/vessel_images/{mmsi}.jpg, strip "
            "those keys from vessel_image_cache.json, and rebuild vessel_cards.json."
        )
    )
    p.add_argument("--input-csv", type=Path, default=default_csv)
    p.add_argument(
        "--aerial-root",
        type=Path,
        default=default_aerial_dataset_root(),
        help="Directory containing ships-aerial-images layout (…/train/images/*.jpg, etc.)",
    )
    p.add_argument("--image-dir", type=Path, default=default_image_dir)
    p.add_argument("--cache-path", type=Path, default=default_cache)
    p.add_argument("--cards-output", type=Path, default=default_cards)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--max-workers", type=int, default=8)
    p.add_argument("--max-side", type=int, default=1024)
    p.add_argument("--quality", type=int, default=85)
    p.add_argument(
        "--public-image-prefix",
        default="/data/vessel_images",
        help="Prefix stored in vessel_cards.json for local JPEG URLs",
    )
    p.add_argument(
        "--clean",
        action="store_true",
        help="Delete existing vessel_images/{mmsi}.jpg for MMSIs in the CSV before writing",
    )
    p.add_argument(
        "--with-summaries",
        action="store_true",
        help="Pass through to build_vessel_cards (Anthropic when configured)",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    summary = assign_aerial_images_to_mmsi(
        input_csv=args.input_csv,
        aerial_root=args.aerial_root,
        image_dir=args.image_dir,
        cache_path=args.cache_path,
        cards_output=args.cards_output,
        seed=args.seed,
        max_workers=args.max_workers,
        max_side=args.max_side,
        quality=args.quality,
        clean_first=args.clean,
        public_image_prefix=args.public_image_prefix,
        with_summaries=args.with_summaries,
    )
    print(
        f"mmsi={summary.mmsi_count} pool={summary.pool_size} "
        f"written={summary.written} failed={summary.failed} "
        f"cache_removed={summary.cache_entries_removed} cards={summary.cards_output}"
    )
    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
