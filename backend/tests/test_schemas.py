"""One round-trip test per schema. Catches Pydantic-config regressions early."""

from datetime import datetime, timezone

from tools.schemas import (
    CaseFile,
    DocumentArtifact,
    FineCalculation,
    IUURule,
    LatLon,
    LegalCitation,
    PenaltyLineItem,
    RegionContext,
    RiskAssessment,
    Vessel,
    VesselDetection,
    VesselEvent,
)


def _roundtrip(obj):
    """Serialize → parse → assert equality on the model dump."""
    cls = type(obj)
    rebuilt = cls.model_validate_json(obj.model_dump_json())
    assert rebuilt.model_dump() == obj.model_dump()


def test_lat_lon():
    _roundtrip(LatLon(lat=-0.75, lon=-90.5))


def test_region_context():
    _roundtrip(
        RegionContext(
            region_id="galapagos",
            name="Galápagos Marine Reserve",
            polygon_geojson={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
            eez_country="ECU",
            mpa_wdpa_ids=[11765],
            rfmo_ids=["IATTC"],
            centroid=LatLon(lat=-0.75, lon=-90.5),
            area_km2=133000.0,
        )
    )


def test_vessel():
    _roundtrip(
        Vessel(
            mmsi="412345678",
            imo="8765432",
            name="LU RONG YUAN YU 666",
            flag="CHN",
            gear_type="longliners",
            length_m=56.0,
            authorizations=[],
            last_position=LatLon(lat=-0.7533, lon=-90.3689),
            last_seen=datetime(2026, 4, 18, 11, 27, tzinfo=timezone.utc),
        )
    )


def test_vessel_event():
    _roundtrip(
        VesselEvent(
            event_id="evt-gap-001",
            mmsi="412345678",
            type="GAP",
            start=datetime(2026, 4, 18, 3, 42, tzinfo=timezone.utc),
            end=datetime(2026, 4, 18, 11, 27, tzinfo=timezone.utc),
            position=LatLon(lat=-1.5383, lon=-91.1450),
            duration_hours=7.75,
            metadata={"reason": "AIS disabled inside protected zone"},
        )
    )


def test_iuu_rule():
    _roundtrip(
        IUURule(
            rule_id="rule-loreg-75a",
            source_doc="https://faolex.fao.org/loreg",
            jurisdiction="ECU",
            category="no_take_zone",
            description="Unauthorized fishing within Galápagos no-take Zone 2.1",
            machine_check={"region_id": "galapagos", "zone": "2.1"},
            penalty_text="USD 80,000 base civil penalty",
        )
    )


def test_legal_citation():
    _roundtrip(
        LegalCitation(
            instrument="PSMA Article 9(4)",
            layer="international",
            full_title="FAO Port State Measures Agreement (2009)",
            role="authority",
            excerpt="Each Party shall deny entry to a port...",
            source_url="https://www.fao.org/port-state-measures",
        )
    )


def test_penalty_line_item():
    cit = LegalCitation(
        instrument="LOREG Art. 75(a)",
        layer="national",
        full_title="Organic Law of the Special Regime for the Province of Galápagos",
        role="penalty",
    )
    _roundtrip(
        PenaltyLineItem(
            description="Unauthorized fishing in Zone 2.1",
            legal_basis=[cit],
            amount_usd=80000.0,
        )
    )


def test_risk_assessment():
    vessel = Vessel(mmsi="412345678", authorizations=[])
    _roundtrip(
        RiskAssessment(
            vessel=vessel,
            region_id="galapagos",
            risk_score=0.92,
            classification="confirmed_iuu",
            triggered_rules=["rule-loreg-75a"],
            evidence=[],
            reasoning="AIS gap inside no-take MPA + unregistered + recidivism.",
        )
    )


def test_fine_calculation():
    cit = LegalCitation(
        instrument="LOREG Art. 75(a)",
        layer="national",
        full_title="Organic Law of the Special Regime for the Province of Galápagos",
        role="penalty",
    )
    item = PenaltyLineItem(description="MPA violation", legal_basis=[cit], amount_usd=80000.0)
    _roundtrip(
        FineCalculation(
            vessel_mmsi="412345678",
            region_id="galapagos",
            estimated_catch_kg=4200.0,
            primary_species="mahi-mahi / yellowfin tuna composite",
            line_items=[item],
            subtotal_usd=80000.0,
            multipliers={"recidivism": 1.25, "cooperation_credit": 1.0},
            total_fine_usd=100000.0,
            citations=[cit],
            breakdown_text="MPA violation × 1.25 recidivism = $100,000.",
        )
    )


def test_document_artifact():
    _roundtrip(
        DocumentArtifact(
            artifact_id="art-001",
            case_id="demo",
            doc_type="notice_of_violation",
            html_url="/static/demo/notice_of_violation.html",
            pdf_url="/static/demo/notice_of_violation.pdf",
            sha256="a3f2b1d4e8c7f6a9b2c5d8e1f4a7b0c3d6e9f2b5a8c1d4e7f0b3a6c9d2e5f8b1",
            rendered_at=datetime(2026, 4, 24, 14, 18, tzinfo=timezone.utc),
            page_count=1,
        )
    )


def test_vessel_detection():
    _roundtrip(
        VesselDetection(
            detection_id="det-sar-001",
            timestamp=datetime(2026, 4, 18, 6, 14, tzinfo=timezone.utc),
            position=LatLon(lat=-1.1344, lon=-90.8592),
            confidence=0.94,
            estimated_length_m=56.0,
            matched_mmsi="412345678",
            source="sar",
            image_url="https://res.cloudinary.com/demo/image/sar-tile.png",
        )
    )


def test_case_file():
    region = RegionContext(
        region_id="galapagos",
        name="Galápagos Marine Reserve",
        polygon_geojson={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
        centroid=LatLon(lat=-0.75, lon=-90.5),
        area_km2=133000.0,
    )
    vessel = Vessel(mmsi="412345678")
    _roundtrip(
        CaseFile(
            case_id="demo",
            region=region,
            vessel=vessel,
            events=[],
            rules=[],
            citations=[],
        )
    )
