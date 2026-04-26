#!/usr/bin/env python3
"""Map Roboflow ship aerial crops onto ``vessel_images/{mmsi}.jpg`` (demo pool, not identity).

The zip layout is ``ships-aerial-images/{train,valid,test}/images/*.{jpg,jpeg,png}``.
MMSIs come from ``vessel_cards.json`` keys plus ``vessel_tracks_global.fallback.json``.

Assignment is deterministic: ``sha256(mmsi) % len(pool)`` into a sorted file list.

Requires Pillow::

    pip install pillow

After copying images, refresh cards (local JPG paths)::

    python -m overfished_ml.image_enrichment.build_all --skip-resolve --skip-download

From repo root, if ``data/datasets/ships-aerial-images`` exists, you can run with **no** ``--pool-root``::

    cd /path/to/overfished && python3 scripts/assign_ship_pool_to_vessel_images.py
    python -m overfished_ml.image_enrichment.build_all --skip-resolve --skip-download

On the DGX after ``scripts/dgx_transfer_archive.sh``, or when the dataset lives elsewhere::

    python3 scripts/assign_ship_pool_to_vessel_images.py \\
      --pool-root ~/datasets/ships-aerial-images \\
      --repo-root ~/overfished

Pull results from DGX to your Mac (adjust remote repo path)::

    rsync -avz asus@gx10-eb94:~/overfished/data/local_pipeline/vessel_images/ ./data/local_pipeline/vessel_images/
    rsync -avz asus@gx10-eb94:~/overfished/data/local_pipeline/vessel_cards.json ./data/local_pipeline/vessel_cards.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from io import BytesIO
from pathlib import Path


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


def _collect_pool_images(roots: list[Path]) -> list[Path]:
    exts = {".jpg", ".jpeg", ".png"}
    found: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        # Prefer YOLO/Roboflow split layout
        for sub in ("train/images", "valid/images", "test/images"):
            d = root / sub
            if not d.is_dir():
                continue
            for p in d.rglob("*"):
                if p.is_file() and p.suffix.lower() in exts:
                    found.append(p)
        if not any((root / s).is_dir() for s in ("train/images", "valid/images", "test/images")):
            for p in root.rglob("*"):
                if p.is_file() and p.suffix.lower() in exts:
                    found.append(p)
    return sorted({p.resolve() for p in found}, key=lambda p: str(p))


def _pool_index(mmsi: str, n: int) -> int:
    h = hashlib.sha256(mmsi.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") % n


def _save_as_jpeg(src: Path, dest: Path, *, max_side: int, quality: int) -> None:
    from PIL import Image, UnidentifiedImageError

    data = src.read_bytes()
    try:
        im = Image.open(BytesIO(data))
    except UnidentifiedImageError:
        shutil.copy2(src, dest)
        return
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    w, h = im.size
    longest = max(w, h)
    if longest > max_side:
        scale = max_side / float(longest)
        im = im.resize(
            (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
            Image.LANCZOS,
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, format="JPEG", quality=quality, optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy aerial ship crops from a pool onto vessel_images/{mmsi}.jpg",
    )
    default_repo = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--pool-root",
        type=Path,
        action="append",
        default=[],
        help="Dataset root (ships-aerial-images). Pass multiple times to merge pools. "
        "If omitted and data/datasets/ships-aerial-images exists under --repo-root, that path is used.",
    )
    parser.add_argument("--repo-root", type=Path, default=default_repo)
    parser.add_argument(
        "--cards",
        type=Path,
        default=Path("data/local_pipeline/vessel_cards.json"),
        help="Relative to --repo-root unless absolute",
    )
    parser.add_argument(
        "--tracks",
        type=Path,
        default=Path("backend/fixtures/vessel_tracks_global.fallback.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/local_pipeline/vessel_images"),
    )
    parser.add_argument("--max-side", type=int, default=1024)
    parser.add_argument("--quality", type=int, default=85)
    parser.add_argument("--limit", type=int, default=0, help="If >0, only process first N MMSIs (sorted)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    default_pool = repo / "data" / "datasets" / "ships-aerial-images"
    pool_arg_list = list(args.pool_root)
    if not pool_arg_list and default_pool.is_dir():
        pool_arg_list = [default_pool]
    if not pool_arg_list:
        print(
            "error: no --pool-root and default dataset directory is missing.\n"
            f"  tried: {default_pool}\n"
            "  pass e.g. --pool-root data/datasets/ships-aerial-images or ~/datasets/ships-aerial-images",
            file=__import__("sys").stderr,
        )
        return 1

    pool_roots = [Path(p).expanduser().resolve() for p in pool_arg_list]
    pool = _collect_pool_images(pool_roots)
    if not pool:
        print("error: no images found under --pool-root", file=__import__("sys").stderr)
        return 1

    cards_path = args.cards if args.cards.is_absolute() else (repo / args.cards).resolve()
    tracks_path = args.tracks if args.tracks.is_absolute() else (repo / args.tracks).resolve()
    out_dir = args.output_dir if args.output_dir.is_absolute() else (repo / args.output_dir).resolve()

    mmsi_set: set[str] = set()
    if cards_path.exists():
        mmsi_set |= {str(k).strip() for k in _load_json_dict(cards_path) if str(k).strip()}
    if tracks_path.exists():
        mmsi_set |= _mmsi_from_tracks(_load_json_list(tracks_path))

    mmsi_list = sorted(mmsi_set)
    if args.limit > 0:
        mmsi_list = mmsi_list[: args.limit]

    if not mmsi_list:
        print("error: no MMSI keys from cards/tracks", file=__import__("sys").stderr)
        return 1

    print(f"pool images: {len(pool)}, MMSIs: {len(mmsi_list)}, output: {out_dir}")

    if args.dry_run:
        for m in mmsi_list[:5]:
            idx = _pool_index(m, len(pool))
            print(f"  example {m} -> {pool[idx].name}")
        print("dry-run; no files written")
        return 0

    try:
        import PIL  # noqa: F401
    except ImportError:
        print("error: install Pillow: pip install pillow", file=__import__("sys").stderr)
        return 1

    n = 0
    for mmsi in mmsi_list:
        src = pool[_pool_index(mmsi, len(pool))]
        dest = out_dir / f"{mmsi}.jpg"
        _save_as_jpeg(src, dest, max_side=args.max_side, quality=args.quality)
        n += 1
        if n % 500 == 0:
            print(f"  wrote {n}/{len(mmsi_list)}")
    print(f"wrote {n} files under {out_dir}")
    print("Next: python -m overfished_ml.image_enrichment.build_all --skip-resolve --skip-download")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
