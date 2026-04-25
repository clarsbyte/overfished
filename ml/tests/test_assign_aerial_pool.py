"""Tests for aerial dataset → MMSI JPEG assignment."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from overfished_ml.image_enrichment.assign_aerial_pool import (  # noqa: E402
    assign_aerial_images_to_mmsi,
    discover_aerial_jpgs,
    unique_sorted_mmsi_from_csv,
)


def _write_rgb_jpeg(path: Path, size: tuple[int, int] = (32, 24)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=(40, 80, 120)).save(path, format="JPEG", quality=90)


def test_discover_aerial_jpgs_finds_train_images(tmp_path: Path) -> None:
    root = tmp_path / "ships-aerial-images"
    j1 = root / "train" / "images" / "a.jpg"
    j2 = root / "valid" / "images" / "b.jpg"
    _write_rgb_jpeg(j1)
    _write_rgb_jpeg(j2)
    found = discover_aerial_jpgs(root)
    assert sorted(found) == sorted([j1, j2])


def test_unique_sorted_mmsi_from_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "g.csv"
    pd.DataFrame({"mmsi": ["9", "1", "9"], "vessel_name": ["a", "b", "c"]}).to_csv(
        csv_path, index=False
    )
    assert unique_sorted_mmsi_from_csv(csv_path) == ["1", "9"]


def test_assign_aerial_images_writes_jpegs_and_cards(tmp_path: Path) -> None:
    aerial = tmp_path / "ships-aerial-images"
    j1 = aerial / "train" / "images" / "x.jpg"
    j2 = aerial / "train" / "images" / "y.jpg"
    _write_rgb_jpeg(j1, (64, 48))
    _write_rgb_jpeg(j2, (48, 64))

    csv_path = tmp_path / "gold.csv"
    pd.DataFrame(
        {
            "mmsi": [100, 200],
            "vessel_name": ["Alpha", "Beta"],
        }
    ).to_csv(csv_path, index=False)

    image_dir = tmp_path / "vessel_images"
    cache_path = tmp_path / "vessel_image_cache.json"
    cache_path.write_text(
        json.dumps({"100": "https://example.com/wrong.jpg", "999": "https://keep.me/x"}),
        encoding="utf-8",
    )
    cards_path = tmp_path / "vessel_cards.json"

    summary = assign_aerial_images_to_mmsi(
        input_csv=csv_path,
        aerial_root=aerial,
        image_dir=image_dir,
        cache_path=cache_path,
        cards_output=cards_path,
        seed=7,
        max_workers=2,
        max_side=256,
        quality=80,
        clean_first=False,
        public_image_prefix="/data/vessel_images",
        with_summaries=False,
    )
    assert summary.mmsi_count == 2
    assert summary.pool_size == 2
    assert summary.written == 2
    assert summary.failed == 0
    assert summary.cache_entries_removed == 1

    assert (image_dir / "100.jpg").is_file()
    assert (image_dir / "200.jpg").is_file()

    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    assert "100" not in cache
    assert cache.get("999") == "https://keep.me/x"

    cards = json.loads(cards_path.read_text(encoding="utf-8"))
    assert cards["100"]["image_path"] == "/data/vessel_images/100.jpg"
    assert cards["200"]["image_path"] == "/data/vessel_images/200.jpg"
    assert "image_source_url" not in cards["100"]
