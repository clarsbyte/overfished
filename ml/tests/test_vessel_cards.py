"""Tests for the vessel-card builder and image downloader."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pandas as pd
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from overfished_ml.image_enrichment.cards import (  # noqa: E402
    build_card_from_row,
    build_vessel_cards,
)
from overfished_ml.image_enrichment.download import download_vessel_images  # noqa: E402


def _make_jpeg_bytes(size: tuple[int, int] = (32, 32), color: tuple[int, int, int] = (200, 50, 50)) -> bytes:
    image = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


def test_build_card_from_row_maps_csv_fields() -> None:
    row: dict[str, Any] = {
        "mmsi": "412217999",
        "vessel_name": "FU XING HAI",
        "vessel_flag": "CHN",
        "vessel_type": "fishing",
        "is_high_risk": False,
        "event_duration_hours": 327.13,
    }
    card = build_card_from_row(row, image_url="https://x/y.jpg", image_path="/data/vessel_images/412217999.jpg")

    assert card.mmsi == "412217999"
    assert card.name == "FU XING HAI"
    assert card.flag == "CHN"
    assert card.vessel_type == "fishing"
    assert card.is_high_risk is False
    assert card.duration_hours == 327.13
    assert card.image_path == "/data/vessel_images/412217999.jpg"
    assert card.image_source_url == "https://x/y.jpg"
    assert card.risk == "safe"

    payload = card.to_dict()
    assert payload["mmsi"] == "412217999"
    assert "summary" not in payload  # None values are omitted


def test_build_card_high_risk_overrides_potential() -> None:
    row = {"mmsi": "1", "is_high_risk": True, "potential_risk": False}
    card = build_card_from_row(row)
    assert card.risk == "high_risk"
    assert card.is_high_risk is True


def test_build_vessel_cards_writes_json_with_local_image(tmp_path: Path) -> None:
    csv = tmp_path / "enriched.csv"
    pd.DataFrame(
        [
            {"mmsi": "1", "vessel_name": "ALPHA", "vessel_flag": "USA", "is_high_risk": True},
            {"mmsi": "2", "vessel_name": "BETA", "vessel_flag": "CHN", "is_high_risk": False},
        ]
    ).to_csv(csv, index=False)
    cache = tmp_path / "vessel_image_cache.json"
    cache.write_text(
        json.dumps({"1": "https://example.com/a.jpg", "2": "https://example.com/b.jpg"}),
        encoding="utf-8",
    )
    image_dir = tmp_path / "vessel_images"
    image_dir.mkdir()
    (image_dir / "1.jpg").write_bytes(_make_jpeg_bytes())

    output = tmp_path / "vessel_cards.json"
    summary = build_vessel_cards(
        input_csv=csv,
        cache_path=cache,
        image_dir=image_dir,
        output_path=output,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert summary.cards_written == 2
    assert summary.with_local_image == 1
    assert summary.with_remote_image == 2
    assert payload["1"]["image_path"] == "/data/vessel_images/1.jpg"
    assert payload["1"]["risk"] == "high_risk"
    assert payload["2"].get("image_path") is None
    assert payload["2"]["image_source_url"] == "https://example.com/b.jpg"


def test_build_vessel_cards_includes_jpg_on_disk_not_in_csv(tmp_path: Path) -> None:
    """Pool-assigned MMSIs get a minimal card so the frontend can show image_path."""
    csv = tmp_path / "enriched.csv"
    pd.DataFrame([{"mmsi": "111111111", "vessel_name": "ONLY_CSV", "is_high_risk": False}]).to_csv(
        csv, index=False
    )
    cache = tmp_path / "vessel_image_cache.json"
    cache.write_text(json.dumps({}), encoding="utf-8")
    image_dir = tmp_path / "vessel_images"
    image_dir.mkdir()
    (image_dir / "111111111.jpg").write_bytes(_make_jpeg_bytes())
    (image_dir / "222222222.jpg").write_bytes(_make_jpeg_bytes(color=(10, 100, 200)))
    output = tmp_path / "vessel_cards.json"
    summary = build_vessel_cards(
        input_csv=csv,
        cache_path=cache,
        image_dir=image_dir,
        output_path=output,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert summary.cards_written == 2
    assert "222222222" in payload
    assert payload["222222222"]["image_path"] == "/data/vessel_images/222222222.jpg"
    assert payload["222222222"]["mmsi"] == "222222222"
    assert "name" not in payload["222222222"]


def test_download_vessel_images_writes_resized_jpegs(tmp_path: Path) -> None:
    cache = tmp_path / "cache.json"
    cache.write_text(
        json.dumps(
            {
                "1": "https://example.com/a.jpg",
                "2": "https://example.com/b.jpg",
                "3": "ftp://nope.example/x",
            }
        ),
        encoding="utf-8",
    )
    image_dir = tmp_path / "vessel_images"
    errors_path = tmp_path / "errors.json"

    big = _make_jpeg_bytes((4000, 2000))

    class _Resp:
        def __init__(self, status: int, body: bytes) -> None:
            self.status_code = status
            self.content = body

    def fake_get(url: str, **kwargs: Any) -> _Resp:
        if url.endswith("a.jpg"):
            return _Resp(200, big)
        if url.endswith("b.jpg"):
            return _Resp(404, b"")
        raise AssertionError(f"unexpected url {url}")

    with patch("overfished_ml.image_enrichment.download.requests.get", side_effect=fake_get):
        summary = download_vessel_images(
            cache_path=cache,
            image_dir=image_dir,
            error_report_path=errors_path,
            max_workers=2,
            max_retries=1,
            backoff_seconds=0,
            max_side=512,
        )

    assert summary.requested == 3
    assert summary.downloaded == 1
    assert summary.failed == 2
    saved = image_dir / "1.jpg"
    assert saved.exists()
    saved_image = Image.open(saved)
    assert max(saved_image.size) == 512
    errors = json.loads(errors_path.read_text(encoding="utf-8"))
    failed_mmsis = {item["mmsi"] for item in errors}
    assert failed_mmsis == {"2", "3"}


def test_download_skips_existing_unless_refresh(tmp_path: Path) -> None:
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps({"1": "https://example.com/a.jpg"}), encoding="utf-8")
    image_dir = tmp_path / "vessel_images"
    image_dir.mkdir()
    (image_dir / "1.jpg").write_bytes(_make_jpeg_bytes())
    errors_path = tmp_path / "errors.json"

    with patch("overfished_ml.image_enrichment.download.requests.get") as mock_get:
        summary = download_vessel_images(
            cache_path=cache,
            image_dir=image_dir,
            error_report_path=errors_path,
            max_retries=1,
            backoff_seconds=0,
        )

    assert summary.skipped_existing == 1
    assert summary.downloaded == 0
    mock_get.assert_not_called()
