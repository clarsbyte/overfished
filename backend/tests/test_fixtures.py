"""Validate that every fixture JSON parses against its Pydantic schema."""

from fixtures._loader import load_model, load_models, load_raw
from tools.schemas import (
    CaseFile,
    FineCalculation,
    IUURule,
    LegalCitation,
    RegionContext,
    Vessel,
    VesselDetection,
    VesselEvent,
)


def test_region_galapagos():
    region = load_model("region_galapagos", RegionContext)
    assert region.region_id == "galapagos"
    assert region.eez_country == "ECU"
    assert 11765 in region.mpa_wdpa_ids


def test_vessels_galapagos():
    vessels = load_models("vessels_galapagos", Vessel)
    assert len(vessels) >= 12
    demo = next(v for v in vessels if v.mmsi == "412345678")
    assert demo.name == "LU RONG YUAN YU 666"
    assert demo.flag == "CHN"
    assert demo.length_m == 56.0


def test_events_412345678():
    events = load_models("events_412345678", VesselEvent)
    assert any(e.type == "GAP" for e in events)
    gap = next(e for e in events if e.type == "GAP")
    assert gap.duration_hours == 7.75


def test_rules_galapagos():
    rules = load_models("rules_galapagos", IUURule)
    assert len(rules) >= 6
    assert any(r.jurisdiction == "ECU" for r in rules)
    assert any(r.category == "no_take_zone" for r in rules)


def test_citations_galapagos():
    citations = load_models("citations_galapagos", LegalCitation)
    layers = {c.layer for c in citations}
    # Plan §3: roster must span layers and have distinct roles per layer
    assert {"international", "national", "rfmo"}.issubset(layers)
    roles = {c.role for c in citations}
    assert len(roles) >= 3


def test_cv_detections_412345678():
    detections = load_models("cv_detections_412345678", VesselDetection)
    sar = [d for d in detections if d.source == "sar"]
    assert sar
    matched = next((d for d in sar if d.matched_mmsi == "412345678"), None)
    assert matched is not None
    assert 0.9 <= matched.confidence <= 1.0


def test_fine_412345678():
    fine = load_model("fine_412345678", FineCalculation)
    assert fine.total_fine_usd == 199875.0
    assert fine.subtotal_usd == 159900.0
    assert sum(li.amount_usd for li in fine.line_items) == 159900.0
    assert fine.multipliers["recidivism"] == 1.25


def test_heatmap_galapagos():
    heatmap = load_raw("heatmap_galapagos")
    assert isinstance(heatmap, list)
    assert len(heatmap) >= 50
    for cell in heatmap:
        assert {"lat", "lon", "hours"}.issubset(cell.keys())
        assert -90.0 <= cell["lat"] <= 90.0
        assert -180.0 <= cell["lon"] <= 180.0


def test_track_412345678():
    track = load_raw("track_412345678")
    assert isinstance(track, list)
    assert len(track) >= 30
    for pt in track:
        assert isinstance(pt, list) and len(pt) == 2


def test_case_dossier():
    case = load_model("case_galapagos_demo", CaseFile)
    assert case.case_id == "IUU-2026-001847"
    assert case.vessel.mmsi == "412345678"
    assert case.fine is not None
    assert case.fine.total_fine_usd == 199875.0
    assert case.risk is not None
    assert case.risk.classification == "confirmed_iuu"
