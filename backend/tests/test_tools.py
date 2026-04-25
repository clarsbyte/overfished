"""Tool layer smoke tests — fixture mode only."""

from __future__ import annotations

import os

os.environ["USE_FIXTURES"] = "1"

from tools import comms, cv_bridge, fines, ports, region, regulations, risk, vessels  # noqa: E402
from tools.schemas import (  # noqa: E402
    CaseFile,
    FineCalculation,
    IUURule,
    LatLon,
    LegalCitation,
    RegionContext,
    RiskAssessment,
    Vessel,
    VesselDetection,
    VesselEvent,
)


# ── region ──────────────────────────────────────────────────────────────


def test_define_region_returns_galapagos():
    r = region.define_region({"type": "Polygon", "coordinates": []})
    assert isinstance(r, RegionContext)
    assert r.region_id == "galapagos"


def test_lookup_eez():
    assert region.lookup_eez(LatLon(lat=-0.5, lon=-90.5)) == "ECU"
    assert region.lookup_eez(LatLon(lat=40.0, lon=-130.0)) is None


def test_lookup_mpas():
    mpas = region.lookup_mpas_in_region("galapagos")
    assert any(m["wdpa_id"] == 11765 for m in mpas)


# ── vessels ─────────────────────────────────────────────────────────────


def test_get_vessels_in_region():
    v = vessels.get_vessels_in_region("galapagos")
    assert isinstance(v, list)
    assert all(isinstance(x, Vessel) for x in v)
    assert any(x.mmsi == "412345678" for x in v)


def test_get_vessel_info():
    v = vessels.get_vessel_info("412345678")
    assert isinstance(v, Vessel)
    assert v.name == "LU RONG YUAN YU 666"


def test_get_vessel_events():
    events = vessels.get_vessel_events("412345678")
    assert any(e.type == "GAP" for e in events)
    filtered = vessels.get_vessel_events("412345678", event_types=["GAP"])
    assert all(e.type == "GAP" for e in filtered)


def test_get_vessel_track():
    track = vessels.get_vessel_track("412345678")
    assert isinstance(track, list)
    assert len(track) > 20
    assert all(len(p) == 2 for p in track)


def test_get_fishing_effort_heatmap():
    heat = vessels.get_fishing_effort_heatmap("galapagos")
    assert isinstance(heat, list)
    assert {"lat", "lon", "hours"}.issubset(heat[0].keys())


def test_get_vessel_iuu_insights():
    insights = vessels.get_vessel_iuu_insights("412345678")
    assert insights["mmsi"] == "412345678"
    assert insights["ais_off_events_90d"] >= 1


# ── regulations ─────────────────────────────────────────────────────────


def test_extract_iuu_rules():
    r = region.define_region({})
    rules = regulations.extract_iuu_rules([], r)
    assert all(isinstance(x, IUURule) for x in rules)
    assert any(r.rule_id == "rule-loreg-75a" for r in rules)


def test_build_citation_roster_dedupes():
    r = region.define_region({})
    rules = regulations.extract_iuu_rules([], r)
    roster = regulations.build_citation_roster(rules, r)
    assert all(isinstance(c, LegalCitation) for c in roster)
    keys = [(c.layer, c.role) for c in roster]
    assert len(keys) == len(set(keys))


def test_evaluate_rule_against_vessel_loreg_triggers():
    r = region.define_region({})
    rules = regulations.extract_iuu_rules([], r)
    loreg = next(rule for rule in rules if rule.rule_id == "rule-loreg-75a")
    v = vessels.get_vessel_info("412345678")
    events = vessels.get_vessel_events("412345678")
    triggered, reasoning = regulations.evaluate_rule_against_vessel(loreg, v, events, r)
    assert triggered is True
    assert reasoning


# ── risk ────────────────────────────────────────────────────────────────


def test_calculate_risk_demo_vessel():
    r = region.define_region({})
    rules = regulations.extract_iuu_rules([], r)
    v = vessels.get_vessel_info("412345678")
    events = vessels.get_vessel_events("412345678")
    detections = cv_bridge.get_cv_detections("galapagos")
    assessment = risk.calculate_risk(v, events, rules, r, detections)
    assert isinstance(assessment, RiskAssessment)
    assert assessment.classification == "confirmed_iuu"
    assert assessment.risk_score >= 0.85


# ── fines ───────────────────────────────────────────────────────────────


def test_estimate_catch_volume():
    v = vessels.get_vessel_info("412345678")
    kg, species = fines.estimate_catch_volume(v, [])
    assert kg == 4200.0
    assert "tuna" in species.lower() or "mahi" in species.lower()


def test_calculate_fine():
    r = region.define_region({})
    rules = regulations.extract_iuu_rules([], r)
    v = vessels.get_vessel_info("412345678")
    events = vessels.get_vessel_events("412345678")
    assessment = risk.calculate_risk(v, events, rules, r)
    citations = regulations.build_citation_roster(rules, r)
    f = fines.calculate_fine(v, assessment, r, rules, citations)
    assert isinstance(f, FineCalculation)
    assert f.total_fine_usd == 199875.0


# ── comms ───────────────────────────────────────────────────────────────


def test_generate_cease_and_desist_audio_url():
    r = region.define_region({})
    rules = regulations.extract_iuu_rules([], r)
    v = vessels.get_vessel_info("412345678")
    events = vessels.get_vessel_events("412345678")
    assessment = risk.calculate_risk(v, events, rules, r)
    url = comms.generate_cease_and_desist_audio(v, assessment, r)
    assert url.endswith(".mp3")
    assert v.mmsi in url


def test_build_cease_and_desist_script():
    v = vessels.get_vessel_info("412345678")
    r = region.define_region({})
    script = comms.build_cease_and_desist_script(v, r)
    assert v.mmsi in script
    assert "cease" in script.lower()


# ── ports ───────────────────────────────────────────────────────────────


def test_lookup_port():
    p = ports.lookup_port("PE CLL")
    assert p is not None
    assert p["name"] == "Callao"
    assert ports.lookup_port("manta") is not None
    assert ports.lookup_port("UNKNOWN") is None


def test_predict_next_port():
    predictions = ports.predict_next_port("412345678")
    assert len(predictions) >= 2
    assert predictions[0]["weight"] >= predictions[-1]["weight"]


def test_notify_port_authority():
    case = CaseFile(
        case_id="demo",
        region=region.define_region({}),
        vessel=vessels.get_vessel_info("412345678"),
        events=[],
        rules=[],
        citations=[],
    )
    port = ports.lookup_port("EC MEC")
    result = ports.notify_port_authority(port, case, "+1-555-0100")
    assert result["status"] == "QUEUED"
    assert result["call_id"]


# ── cv_bridge ───────────────────────────────────────────────────────────


def test_get_cv_detections():
    detections = cv_bridge.get_cv_detections("galapagos")
    assert all(isinstance(d, VesselDetection) for d in detections)
    sar_for_demo = next(
        (d for d in detections if d.source == "sar" and d.matched_mmsi == "412345678"), None
    )
    assert sar_for_demo is not None
