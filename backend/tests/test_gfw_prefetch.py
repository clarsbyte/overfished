"""Unit tests for the GFW response → fleet-record transformation.

No network calls. We feed a saved-shape sample response (a real GFW
4Wings vessel-presence response with the dataset version key intact) and
assert the flatten/group/classify logic produces the expected fleet shape.

Sample fixture: ``tests/sample_fixtures/gfw_sample_response.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.gfw_prefetch import (
    _classify_track_points,
    _flatten_report,
    _group_by_vessel,
    _vessel_record,
)

SAMPLE = Path(__file__).parent / "sample_fixtures" / "gfw_sample_response.json"


def _load_sample() -> dict:
    return json.loads(SAMPLE.read_text())


def test_flatten_drops_dataset_key():
    rows = _flatten_report(_load_sample())
    # 4 + 3 + 1 + 1 = 9 raw rows in the sample
    assert len(rows) == 9
    assert all("vesselId" in r for r in rows)


def test_group_by_vessel_uses_vesselId():
    rows = _flatten_report(_load_sample())
    grouped = _group_by_vessel(rows)
    assert "demo-A" in grouped and len(grouped["demo-A"]) == 4
    assert "demo-B" in grouped and len(grouped["demo-B"]) == 3
    assert "demo-C-too-short" in grouped


def test_classify_track_points_sorted_and_skips_nulls():
    rows = _flatten_report(_load_sample())
    grouped = _group_by_vessel(rows)
    # demo-A: should produce 4 points sorted by date
    pts = _classify_track_points(grouped["demo-A"])
    assert pts == [[-1.5, -91.1], [-1.4, -91.0], [-1.3, -90.9], [-1.2, -90.8]]


def test_vessel_record_filters_short_tracks():
    rows = _flatten_report(_load_sample())
    grouped = _group_by_vessel(rows)
    # MIN_TRACK_POINTS = 3, so demo-A (4) and demo-B (3) pass; demo-C (1) fails
    assert _vessel_record(grouped["demo-A"], "confirmed_iuu") is not None
    assert _vessel_record(grouped["demo-B"], "high_risk") is not None
    assert _vessel_record(grouped["demo-C-too-short"], "suspect") is None


def test_vessel_record_filters_null_coords():
    rows = _flatten_report(_load_sample())
    grouped = _group_by_vessel(rows)
    # demo-D has 1 row with null lat/lon → after filtering, 0 points → rejected
    rec = _vessel_record(grouped["demo-D-no-coords"], "suspect")
    assert rec is None


def test_vessel_record_carries_identity():
    rows = _flatten_report(_load_sample())
    grouped = _group_by_vessel(rows)
    rec = _vessel_record(grouped["demo-A"], "confirmed_iuu")
    assert rec is not None
    assert rec["mmsi"] == "412345678"
    assert rec["name"] == "LU RONG YUAN YU 666"
    assert rec["flag"] == "CHN"
    assert rec["risk"] == "confirmed_iuu"
    assert len(rec["points"]) == 4
    # All points are [lat, lon] pairs
    assert all(len(p) == 2 for p in rec["points"])


def test_real_fixture_well_formed():
    """The committed prefetch output should also pass validation."""
    fp = Path(__file__).parent.parent / "fixtures" / "vessel_tracks_global.json"
    if not fp.exists():
        return  # no prefetch run yet — skip silently
    data = json.loads(fp.read_text())
    assert isinstance(data, list)
    if not data:
        return
    sample = data[0]
    assert {"mmsi", "name", "flag", "risk", "points"}.issubset(sample.keys())
    assert all(isinstance(p, list) and len(p) == 2 for p in sample["points"])
