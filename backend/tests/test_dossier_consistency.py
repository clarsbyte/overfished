"""Cross-fixture consistency checks — catches drift between primitives.

The dossier is the source of truth. Each primitive fixture must agree with it on
the demo narrative (timestamps, totals, last-known position).
"""

from datetime import datetime, timezone

from fixtures._loader import load_model, load_models, load_raw
from tools.schemas import CaseFile, FineCalculation, Vessel, VesselEvent


def test_ais_gap_end_matches_last_seen():
    events = load_models("events_412345678", VesselEvent)
    vessels = load_models("vessels_galapagos", Vessel)

    gap = next(e for e in events if e.type == "GAP")
    demo = next(v for v in vessels if v.mmsi == "412345678")

    assert gap.end is not None
    assert demo.last_seen is not None
    assert gap.end == demo.last_seen, (
        f"GAP end {gap.end} must equal vessel last_seen {demo.last_seen}; "
        "the WHEREAS clauses in notice_of_violation.html cite this single timestamp."
    )


def test_fine_total_matches_dossier():
    fine = load_model("fine_412345678", FineCalculation)
    case = load_model("case_galapagos_demo", CaseFile)
    assert case.fine is not None
    assert case.fine.total_fine_usd == fine.total_fine_usd == 199875.0


def test_track_endpoint_matches_last_position():
    track = load_raw("track_412345678")
    vessels = load_models("vessels_galapagos", Vessel)
    demo = next(v for v in vessels if v.mmsi == "412345678")

    assert demo.last_position is not None
    last_pt = track[-1]
    assert abs(last_pt[0] - demo.last_position.lat) < 1e-3
    assert abs(last_pt[1] - demo.last_position.lon) < 1e-3


def test_track_starts_at_gap_origin():
    """The trajectory should begin near the last AIS-on position before the gap."""
    track = load_raw("track_412345678")
    events = load_models("events_412345678", VesselEvent)
    gap = next(e for e in events if e.type == "GAP")

    first_pt = track[0]
    # gap.position is the first AIS-off coordinate; track may start slightly earlier
    assert abs(first_pt[0] - gap.position.lat) < 0.2
    assert abs(first_pt[1] - gap.position.lon) < 0.3


def test_dossier_gap_event_present():
    case = load_model("case_galapagos_demo", CaseFile)
    gaps = [e for e in case.events if e.type == "GAP"]
    assert len(gaps) == 1
    assert gaps[0].end == datetime(2026, 4, 18, 11, 27, tzinfo=timezone.utc)


def test_recidivism_referenced_in_dossier():
    """Prior offense in Peru EEZ (2024-09-03) drives the 1.25 recidivism multiplier."""
    events = load_models("events_412345678", VesselEvent)
    fine = load_model("fine_412345678", FineCalculation)

    prior = [e for e in events if e.type == "PORT_VISIT" and e.metadata.get("prior_offense")]
    assert prior, "events_412345678 must include the 2024-09-03 PORT_VISIT to Callao"
    assert fine.multipliers["recidivism"] == 1.25
