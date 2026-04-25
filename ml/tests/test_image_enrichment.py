"""Tests for vessel image enrichment workflow."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from overfished_ml.image_enrichment.enricher import enrich_dataset_with_ship_image_urls  # noqa: E402


def test_enrich_dry_run_adds_column_and_miss_report(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    cache_path = tmp_path / "cache.json"
    miss_report = tmp_path / "misses.json"

    pd.DataFrame(
        [
            {"mmsi": "111000111", "vessel_name": "ALPHA"},
            {"mmsi": "222000222", "vessel_name": "BETA"},
            {"mmsi": "111000111", "vessel_name": "ALPHA"},
        ]
    ).to_csv(input_csv, index=False)

    summary = enrich_dataset_with_ship_image_urls(
        input_csv=input_csv,
        output_csv=output_csv,
        cache_path=cache_path,
        miss_report_path=miss_report,
        api_key=None,
        base_url="https://services.marinetraffic.com/api",
        timeout_seconds=1,
        dry_run=True,
    )

    enriched = pd.read_csv(output_csv)
    assert "ship_image_url" in enriched.columns
    assert enriched["ship_image_url"].fillna("").eq("").all()
    assert summary.unique_vessels == 2
    assert summary.misses == 2

    misses_payload = json.loads(miss_report.read_text(encoding="utf-8"))
    assert len(misses_payload) == 2
    assert all(item["status"] == "dry_run" for item in misses_payload)


def test_override_csv_resolves_without_api(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    overrides_csv = tmp_path / "overrides.csv"
    output_csv = tmp_path / "output.csv"
    cache_path = tmp_path / "cache.json"
    miss_report = tmp_path / "misses.json"

    pd.DataFrame(
        [
            {"mmsi": "999888777", "vessel_name": "TEST BOAT"},
        ]
    ).to_csv(input_csv, index=False)
    pd.DataFrame(
        [
            {
                "mmsi": "999888777",
                "ship_image_url": "https://example.com/manual-vessel.png",
            }
        ]
    ).to_csv(overrides_csv, index=False)

    summary = enrich_dataset_with_ship_image_urls(
        input_csv=input_csv,
        output_csv=output_csv,
        cache_path=cache_path,
        miss_report_path=miss_report,
        api_key=None,
        base_url="https://services.marinetraffic.com/api",
        timeout_seconds=1,
        dry_run=False,
        override_csv_path=overrides_csv,
        use_commons_fallback=False,
    )

    enriched = pd.read_csv(output_csv)
    assert enriched["ship_image_url"].iloc[0].startswith("https://")
    assert summary.override_hits == 1
    assert summary.commons_hits == 0
    assert summary.misses == 0


def test_offline_mode_never_calls_remote_sources(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    cache_path = tmp_path / "cache.json"
    miss_report = tmp_path / "misses.json"

    pd.DataFrame([{"mmsi": "123456789", "vessel_name": "GHOST"}]).to_csv(input_csv, index=False)

    summary = enrich_dataset_with_ship_image_urls(
        input_csv=input_csv,
        output_csv=output_csv,
        cache_path=cache_path,
        miss_report_path=miss_report,
        api_key="fake-would-fail-if-used",
        base_url="https://services.marinetraffic.com/api",
        timeout_seconds=1,
        offline=True,
        use_commons_fallback=True,
    )

    assert summary.marine_traffic_hits == 0
    assert summary.commons_hits == 0
    assert summary.misses == 1
    misses_payload = json.loads(miss_report.read_text(encoding="utf-8"))
    assert misses_payload[0]["status"] == "offline_unresolved"


def test_offline_uses_cache_without_network(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    cache_path = tmp_path / "cache.json"
    miss_report = tmp_path / "misses.json"

    cache_path.write_text('{"123456789": "https://example.com/from-cache.png"}', encoding="utf-8")
    pd.DataFrame([{"mmsi": "123456789", "vessel_name": "CACHED"}]).to_csv(input_csv, index=False)

    summary = enrich_dataset_with_ship_image_urls(
        input_csv=input_csv,
        output_csv=output_csv,
        cache_path=cache_path,
        miss_report_path=miss_report,
        api_key="fake",
        base_url="https://services.marinetraffic.com/api",
        timeout_seconds=1,
        offline=True,
    )

    assert summary.cache_hits == 1
    assert summary.misses == 0
    enriched = pd.read_csv(output_csv)
    assert enriched["ship_image_url"].iloc[0].startswith("https://")
