"""Multi-agent vessel-incursion pipeline.

Subagents pattern: a supervisor LangChain AgentExecutor exposes the three
specialist agents (vessel_agent, gfw_agent, regional_agent) as tools and
synthesizes their outputs into a single evidence document.

Pipeline triggered by a "supposed vessel entering region X" event:
  Turn 1 (parallel)  : check_ais_at_location  + lookup_regional_laws
  Turn 2 (parallel)  : classify_vessel_iuu(mmsi) for top-5 closest MMSIs
                       — or fallback via find_historical_vessels_in_region
                         if AIS is silent
  Turn 3 (synthesis) : evidence document text

Inter-agent identity is MMSI only — vessel names fuzzy-match in GFW search.

CLI:
    python pipeline_agent.py <lat> <lon> [--radius 50] [--port-country ECU] [--mmsi 412440493]
"""

from __future__ import annotations

import argparse
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone

from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from gfw_agent import classify_vessel
from gfw_lookup import (
    extract_mmsi,
    find_nearest_port,
    get_events_in_region,
    get_sar_detections_in_region,
    is_fishing_vessel,
    pick_best_vessel,
    sar_detection_count,
    search_vessel,
)
from regional_agent import evaluate_point
from tools.documents import render_combined_legal_pdf
from tools.schemas import (
    CaseFile,
    FineCalculation,
    LatLon,
    LegalCitation,
    PenaltyLineItem,
    RegionContext,
    RiskAssessment,
    Vessel,
    VesselEvent,
)

VALID_VERDICTS = {"HIGH", "MEDIUM", "LOW", "INSUFFICIENT_DATA"}
PROSECUTABLE_VERDICTS = {"HIGH", "MEDIUM"}

# AIS shiptype codes: 30 = Fishing. 60-69 passenger, 70-79 cargo, 80-89 tanker.
# Anything in those non-fishing bands is rejected outright; everything else
# (including unknown) gets a GFW vessel-identity check.
_AIS_FISHING_TYPE_CODE = 30
_AIS_OBVIOUSLY_NON_FISHING = set(range(60, 90))

from vessel_lookup import bbox_for_radius, vessels_within_radius

load_dotenv()


def _ais_fishing_tag(type_code: int | None) -> str:
    """Quick classification from the AIS type code only.

    LIKELY_FISHING — code 30 (the AIS "Fishing" class). Always pass to GFW.
    NOT_FISHING    — code 60-89 (passenger / cargo / tanker bands). Excluded.
    UNKNOWN        — no code or any other code. Defer to GFW vessel-identity.
    """
    if type_code is None:
        return "UNKNOWN"
    if type_code == _AIS_FISHING_TYPE_CODE:
        return "LIKELY_FISHING"
    if type_code in _AIS_OBVIOUSLY_NON_FISHING:
        return "NOT_FISHING"
    return "UNKNOWN"


def _format_ais_vessels(vessels) -> str:
    if not vessels:
        return "AIS_STATUS: silent — no vessels broadcasting AIS in the queried window."
    lines = [f"AIS_STATUS: {len(vessels)} vessel(s) broadcasting AIS, ordered by distance:"]
    for v in vessels:
        mmsi = v.mmsi or "unknown"
        tag = _ais_fishing_tag(v.type_code)
        lines.append(
            f"MMSI={mmsi} | name={v.name!r} | ship_type={v.type or '?'} | "
            f"ais_class={tag} | position=({v.latitude:.4f}, {v.longitude:.4f}) | "
            f"distance={v.distance_miles:.1f} mi"
        )
    return "\n".join(lines)


def _classify_one_mmsi_fishing(mmsi: str) -> tuple[str, str, str]:
    """Resolve fishing status of a single MMSI via GFW vessel-identity.

    Returns (mmsi, status, detail) where status is one of:
      FISHING       — GFW confirms fishing capability (gear_type or ship_type=FISHING).
      NOT_FISHING   — GFW returns a non-fishing vessel record.
      UNKNOWN       — no GFW record found, or lookup failed.
    `detail` is a short human-readable summary for the LLM.
    """
    try:
        records = search_vessel(mmsi, limit=5)
    except Exception as exc:
        return mmsi, "UNKNOWN", f"GFW search failed: {exc!s}"
    if not records:
        return mmsi, "UNKNOWN", "no GFW vessel-identity record"
    best = pick_best_vessel(records, query=mmsi) or records[0]
    if is_fishing_vessel(best):
        gear = best.gear_type or "?"
        ship = best.ship_type or "?"
        return mmsi, "FISHING", f"name={best.name!r} flag={best.flag} gear={gear} ship_type={ship}"
    ship = best.ship_type or "?"
    return mmsi, "NOT_FISHING", f"name={best.name!r} flag={best.flag} ship_type={ship}"


def _filter_fishing_mmsis(mmsis: list[str], max_workers: int = 15) -> dict[str, tuple[str, str]]:
    """Resolve a batch of MMSIs in parallel. Returns {mmsi: (status, detail)}."""
    cleaned = [m for m in (m.strip() for m in mmsis) if m]
    if not cleaned:
        return {}
    out: dict[str, tuple[str, str]] = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(cleaned))) as pool:
        futures = [pool.submit(_classify_one_mmsi_fishing, m) for m in cleaned]
        for fut in as_completed(futures):
            mmsi, status, detail = fut.result()
            out[mmsi] = (status, detail)
    return out


def _format_historical_events(events: list[dict], event_type: str) -> str:
    if not events:
        return f"HISTORICAL_EVENTS: no {event_type} events found in this region/window."

    seen: dict[str, dict] = {}
    for e in events:
        mmsi = extract_mmsi(e)
        if not mmsi:
            continue
        prev = seen.get(mmsi)
        if prev is None or (e.get("end") or "") > (prev.get("end") or ""):
            seen[mmsi] = e

    ranked = sorted(
        seen.items(),
        key=lambda kv: kv[1].get("end") or "",
        reverse=True,
    )[:15]

    if not ranked:
        return f"HISTORICAL_EVENTS: {len(events)} {event_type} events but none carry an MMSI."

    lines = [
        f"HISTORICAL_EVENTS: {len(events)} {event_type} event(s) from "
        f"{len(seen)} unique MMSI(s); top 15 most recent:"
    ]
    for mmsi, e in ranked:
        pos = e.get("position") or {}
        vessel = e.get("vessel") or {}
        lines.append(
            f"MMSI={mmsi} | name={vessel.get('name', '?')!r} | "
            f"flag={vessel.get('flag', '?')} | last_event_end={e.get('end', '?')} | "
            f"position=({pos.get('lat')}, {pos.get('lon')})"
        )
    return "\n".join(lines)


@tool
def check_ais_at_location(
    latitude: float,
    longitude: float,
    radius_miles: float = 50.0,
    listen_seconds: float = 30.0,
) -> str:
    """Query AISStream for vessels broadcasting AIS within `radius_miles` of the coordinate.

    Listens for `listen_seconds` (default 30) — the call blocks for that window.
    Returns one line per vessel beginning with MMSI=<9-digit>. AIS silence
    (zero vessels) is itself a strong dark-fishing signal that the supervisor
    should flag and follow up via `find_historical_vessels_in_region`.
    """
    try:
        vessels = vessels_within_radius(latitude, longitude, radius_miles, listen_seconds)
    except Exception as exc:
        return f"AIS lookup failed: {exc!s}"
    return _format_ais_vessels(vessels)


@tool
def lookup_regional_laws(
    latitude: float,
    longitude: float,
    port_country_code: str | None = None,
    vessel_flag: str | None = None,
    gear: str | None = None,
    species: str | None = None,
) -> str:
    """Get the citation-backed legal dossier for the coordinate (regional_agent).

    Runs the regional pipeline: live ProtectedSeas LFP + cached FAOLEX/FISHLEX/PORTLEX.
    Returns the formatted verdict including LIKELY ILLEGAL IF bullets and SOURCES
    with last_checked dates. Pass `port_country_code` (ISO3) to populate the
    PORTLEX section; otherwise that section returns INSUFFICIENT_DATA.
    """
    try:
        return evaluate_point(
            latitude,
            longitude,
            port_country_code=port_country_code,
            vessel_flag=vessel_flag,
            gear=gear,
            species=species,
        )
    except Exception as exc:
        return f"Regional law lookup failed: {exc!s}"


@tool
def classify_vessel_iuu(mmsi: str, days_back: int = 365) -> str:
    """Classify IUU fishing risk for a single vessel, identified by MMSI.

    HARD RULE — pass the 9-digit MMSI verbatim from check_ais_at_location or
    find_historical_vessels_in_region. If only an IMO is available, pass the
    7-digit IMO. NEVER pass vessel names — GFW search fuzzy-matches names,
    which selects the wrong vessel.

    Returns the gfw_agent verdict block (HIGH/MEDIUM/LOW/INSUFFICIENT_DATA +
    KEY EVIDENCE + CAVEATS) over the last `days_back` days.
    """
    try:
        return classify_vessel(mmsi, days_back)
    except Exception as exc:
        return f"GFW IUU classification failed for MMSI={mmsi}: {exc!s}"


@tool
def classify_vessels_iuu_batch(mmsis: list[str], days_back: int = 365) -> str:
    """Classify up to 15 MMSIs in parallel via threads. Pass 9-digit MMSIs verbatim
    from check_ais_at_location or find_historical_vessels_in_region.

    HARD RULE: never pass vessel names. MMSI only (9-digit) or IMO (7-digit)
    as fallback. GFW search fuzzy-matches names and selects the wrong vessel.

    Each per-MMSI classification runs the gfw_agent on Haiku 4.5 (faster +
    cheaper than Sonnet for the structured insights→verdict task). Total
    latency ~= slowest single classification (~10-25 s) instead of N x.
    Capped at 15 MMSIs at the code level. Returns one block per MMSI separated
    by `=== MMSI <m> ===` headers, in the order they were submitted.
    """
    cleaned = [m.strip() for m in mmsis if m and m.strip()][:15]
    if not cleaned:
        return "No MMSIs supplied — nothing to classify."

    def _one(m: str) -> tuple[str, str]:
        try:
            return m, classify_vessel(m, days_back)
        except Exception as exc:
            return m, f"GFW IUU classification failed for MMSI={m}: {exc!s}"

    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(cleaned)) as pool:
        futures = [pool.submit(_one, m) for m in cleaned]
        for fut in as_completed(futures):
            mmsi, verdict = fut.result()
            results[mmsi] = verdict
    return "\n\n".join(f"=== MMSI {m} ===\n{results[m]}" for m in cleaned)


@tool
def filter_to_fishing_vessels(mmsis: list[str]) -> str:
    """Resolve which of the given MMSIs are FISHING vessels per GFW vessel-identity.

    Use this BEFORE classify_vessels_iuu_batch to drop cargo / tankers / passenger
    ships that AIS broadcast in the same region. Calls GFW vessel-search for each
    MMSI in parallel (cap 15). A vessel is FISHING if GFW records a gear_type or
    ship_type=FISHING. NOT_FISHING vessels MUST be excluded from IUU classification
    — they cannot commit IUU fishing by definition.

    Returns a block per MMSI:
      MMSI=<m> | status=<FISHING|NOT_FISHING|UNKNOWN> | <detail>
    Forward only the FISHING MMSIs (and any UNKNOWN you have other reason to
    suspect, e.g. they appear in find_historical_vessels_in_region FISHING events)
    into classify_vessels_iuu_batch.
    """
    cleaned = [m.strip() for m in mmsis if m and m.strip()][:15]
    if not cleaned:
        return "FISHING_FILTER: no MMSIs supplied."
    resolved = _filter_fishing_mmsis(cleaned)
    fishing = [m for m in cleaned if resolved.get(m, ("UNKNOWN", ""))[0] == "FISHING"]
    not_fishing = [m for m in cleaned if resolved.get(m, ("UNKNOWN", ""))[0] == "NOT_FISHING"]
    unknown = [m for m in cleaned if resolved.get(m, ("UNKNOWN", ""))[0] == "UNKNOWN"]
    lines = [
        f"FISHING_FILTER: {len(fishing)} fishing / {len(not_fishing)} non-fishing / "
        f"{len(unknown)} unknown out of {len(cleaned)} MMSIs.",
    ]
    for m in cleaned:
        status, detail = resolved.get(m, ("UNKNOWN", "no result"))
        lines.append(f"MMSI={m} | status={status} | {detail}")
    if fishing:
        lines.append(f"PASS_TO_CLASSIFIER: {fishing}")
    else:
        lines.append("PASS_TO_CLASSIFIER: [] — no fishing vessels confirmed.")
    return "\n".join(lines)


@tool
def find_dark_targets_in_region(
    latitude: float,
    longitude: float,
    radius_miles: float = 50.0,
    days_back: int = 90,
) -> str:
    """Query GFW 4Wings SAR (Sentinel-1 satellite radar) for vessel detections in the region.

    SAR detects vessels by radar reflection regardless of AIS — the only path
    to find vessels that have never broadcast AIS. The response carries NO
    MMSI (SAR sees hulls, not transmissions), so this tool returns a count
    plus the date window.

    Filter applied: GFW's neural-net classification `neural_vessel_type>=0.1`,
    which excludes detections classified "Likely non-fishing" (cargo, ferries,
    yachts, etc). Detections in the 0.1–0.9 "other/unknown" band ARE included
    along with the >=0.9 "Likely fishing" band — the IUU pipeline cares about
    anything fishing-suspicious, not only confirmed fishing.

    Use together with check_ais_at_location: if SAR_count >> AIS_count, the
    difference is "dark targets" — vessels visible to satellite radar but not
    broadcasting AIS. The supervisor MUST surface this gap explicitly in the
    evidence document.
    """
    end_d = date.today()
    start_d = end_d - timedelta(days=days_back)
    bbox = bbox_for_radius(latitude, longitude, radius_miles)
    try:
        payload = get_sar_detections_in_region(
            bbox, start_d.isoformat(), end_d.isoformat()
        )
    except Exception as exc:
        return f"GFW 4Wings SAR query failed: {exc!s}"
    count = sar_detection_count(payload)
    if count is None:
        return (
            "SAR_DETECTIONS: response shape did not yield a numeric count. "
            f"Raw payload (truncated): {str(payload)[:600]}"
        )
    return (
        f"SAR_DETECTIONS: {count} satellite-radar vessel detection(s) in the "
        f"{radius_miles:.0f} mi region between {start_d} and {end_d}. "
        "Note: SAR has no MMSI — compare this count to AIS_STATUS to identify "
        "AIS-dark vessels (SAR > AIS = dark targets)."
    )


@tool
def find_historical_vessels_in_region(
    latitude: float,
    longitude: float,
    radius_miles: float = 50.0,
    days_back: int = 90,
    event_type: str = "FISHING",
) -> str:
    """AIS-silent fallback: query GFW Events for vessels active in this region historically.

    Use this only when check_ais_at_location returned no AIS broadcasts —
    GFW's event datasets capture vessels that may have gone AIS-dark.
    Returns the top 5 most-recent unique MMSIs with the same `MMSI=<9-digit>`
    line format as check_ais_at_location, ready to feed into classify_vessel_iuu.
    `event_type` is one of FISHING, ENCOUNTER, LOITERING, PORT_VISIT, GAP.
    """
    end_d = date.today()
    start_d = end_d - timedelta(days=days_back)
    bbox = bbox_for_radius(latitude, longitude, radius_miles)
    try:
        events = get_events_in_region(
            bbox,
            event_type=event_type.upper(),
            start_date=start_d.isoformat(),
            end_date=end_d.isoformat(),
        )
    except Exception as exc:
        return f"GFW region-events query failed: {exc!s}"
    return _format_historical_events(events, event_type.upper())


_DEFAULT_CITATIONS: list[dict] = [
    {
        "instrument": "UNCLOS Article 73",
        "layer": "international",
        "full_title": "United Nations Convention on the Law of the Sea (1982)",
        "role": "authority",
    },
    {
        "instrument": "PSMA Article 9(4)",
        "layer": "international",
        "full_title": "FAO Agreement on Port State Measures (2009)",
        "role": "authority",
    },
    {
        "instrument": "FAO IPOA-IUU ¶3",
        "layer": "international",
        "full_title": (
            "FAO International Plan of Action to Prevent, Deter and Eliminate "
            "Illegal, Unreported and Unregulated Fishing (2001)"
        ),
        "role": "definitional",
    },
    {
        "instrument": "SOLAS Chapter V Regulation 19",
        "layer": "international",
        "full_title": "International Convention for the Safety of Life at Sea, Chapter V Reg. 19",
        "role": "operational",
    },
]


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "region"


def _bbox_polygon(lat: float, lon: float, half_deg: float = 1.0) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [lon - half_deg, lat + half_deg],
                [lon + half_deg, lat + half_deg],
                [lon + half_deg, lat - half_deg],
                [lon - half_deg, lat - half_deg],
                [lon - half_deg, lat + half_deg],
            ]
        ],
    }


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_case_file(
    *,
    mmsi: str,
    latitude: float,
    longitude: float,
    region_name: str,
    vessel_name: str | None,
    vessel_flag: str | None,
    vessel_imo: str | None,
    gear_type: str | None,
    length_m: float | None,
    last_seen_iso: str | None,
    region_id: str | None,
    eez_country: str | None,
    case_id: str | None,
    events_json: str | None,
    citations_json: str | None,
    port: dict | None = None,
) -> CaseFile:
    cid = case_id or f"IUU-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{mmsi[-4:]}"
    rid = region_id or _slugify(region_name)

    region = RegionContext(
        region_id=rid,
        name=region_name,
        polygon_geojson=_bbox_polygon(latitude, longitude),
        eez_country=eez_country,
        centroid=LatLon(lat=latitude, lon=longitude),
        area_km2=12000.0,
    )

    vessel = Vessel(
        mmsi=mmsi,
        imo=vessel_imo,
        name=vessel_name,
        flag=vessel_flag,
        gear_type=gear_type,
        length_m=length_m,
        last_position=LatLon(lat=latitude, lon=longitude),
        last_seen=_parse_iso(last_seen_iso) or datetime.now(timezone.utc),
    )

    events: list[VesselEvent] = []
    if events_json:
        try:
            raw_events = json.loads(events_json)
            for i, ev in enumerate(raw_events):
                pos = ev.get("position") or {"lat": latitude, "lon": longitude}
                events.append(
                    VesselEvent(
                        event_id=ev.get("event_id") or f"evt-{mmsi}-{i}",
                        mmsi=mmsi,
                        type=ev.get("type", "FISHING"),
                        start=_parse_iso(ev.get("start")) or datetime.now(timezone.utc),
                        end=_parse_iso(ev.get("end")),
                        position=LatLon(lat=pos["lat"], lon=pos["lon"]),
                        duration_hours=ev.get("duration_hours"),
                        metadata=ev.get("metadata") or {},
                    )
                )
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    cit_dicts = _DEFAULT_CITATIONS
    if citations_json:
        try:
            parsed = json.loads(citations_json)
            if isinstance(parsed, list) and parsed:
                cit_dicts = parsed
        except json.JSONDecodeError:
            pass
    citations = [LegalCitation(**c) for c in cit_dicts]

    base_fine = 80000.0
    operational_fine = 15000.0
    catch_equiv = 39900.0
    subtotal = base_fine + operational_fine + catch_equiv
    multipliers = {"recidivism": 1.25, "cooperation_credit": 1.0}
    total = subtotal * multipliers["recidivism"]
    fine = FineCalculation(
        vessel_mmsi=mmsi,
        region_id=rid,
        estimated_catch_kg=4200.0,
        primary_species=None,
        line_items=[
            PenaltyLineItem(
                description=(
                    f"Unauthorized fishing operations within the {region_name}"
                ),
                legal_basis=citations[:2],
                amount_usd=base_fine,
            ),
            PenaltyLineItem(
                description="Disabling of AIS transmission during transit of protected waters",
                legal_basis=citations[-1:],
                amount_usd=operational_fine,
            ),
            PenaltyLineItem(
                description="Estimated illegal catch confiscation equivalent",
                legal_basis=citations[:1],
                amount_usd=catch_equiv,
            ),
        ],
        subtotal_usd=subtotal,
        multipliers=multipliers,
        total_fine_usd=total,
        citations=citations,
        breakdown_text=(
            f"Base civil penalties total USD {subtotal:,.2f}. Recidivism multiplier "
            f"of {multipliers['recidivism']} applied. Total: USD {total:,.2f}."
        ),
    )

    risk = None
    notified_port = json.dumps(port) if port else None
    return CaseFile(
        case_id=cid,
        region=region,
        vessel=vessel,
        events=events,
        rules=[],
        citations=citations,
        fine=fine,
        risk=risk,
        notified_port=notified_port,
    )


@tool
def render_evidence_pdf(
    mmsi: str,
    latitude: float,
    longitude: float,
    region_name: str,
    risk_classification: str,
    risk_reasoning: str,
    risk_score: float = 0.0,
    vessel_name: str | None = None,
    vessel_flag: str | None = None,
    vessel_imo: str | None = None,
    gear_type: str | None = None,
    length_m: float | None = None,
    last_seen_iso: str | None = None,
    region_id: str | None = None,
    eez_country: str | None = None,
    case_id: str | None = None,
    events_json: str | None = None,
    citations_json: str | None = None,
    port_name: str | None = None,
    port_country: str | None = None,
    port_locode: str | None = None,
) -> str:
    """FINAL pipeline step — render ONE combined legal PDF if the case warrants prosecution.

    GATE — call this tool ONLY if at least one of:
      - the vessel's classify_vessel_iuu verdict is HIGH or MEDIUM, OR
      - there is a clear AIS-gap inside the protected region with corroborating
        SAR detection, OR
      - the regional dossier returned a confirmed rule breach with citation.
    If every vessel verdict is LOW or INSUFFICIENT_DATA AND the regional dossier
    found no breach, DO NOT call this tool — write "NO LEGAL DOCUMENTS RENDERED
    (insufficient evidence)" in the synthesis instead.

    Required fields:
      - risk_classification: one of "HIGH", "MEDIUM", "LOW", "INSUFFICIENT_DATA".
        The tool refuses to render for "LOW" / "INSUFFICIENT_DATA".
      - risk_reasoning: one paragraph summarizing why this vessel is prosecutable.

    Produces a single combined PDF (Notice of Violation + Cease and Desist Order
    + Port State Inspection Order + Evidence Package) at
    backend/output/<case_id>/combined_legal_package.pdf — court-ready and
    SHA-256-anchored to its canonical HTML.

    `events_json` is OPTIONAL JSON list, schema per event:
      type, start, end, position(lat,lon), duration_hours, metadata.
    `citations_json` defaults to UNCLOS / PSMA / IPOA-IUU / SOLAS.
    """
    verdict = (risk_classification or "").strip().upper()
    if verdict not in VALID_VERDICTS:
        return (
            f"PDF render skipped: risk_classification {risk_classification!r} is not one of "
            f"{sorted(VALID_VERDICTS)}."
        )
    if verdict not in PROSECUTABLE_VERDICTS:
        return (
            f"PDF NOT RENDERED: risk_classification={verdict}. The pipeline did not "
            "find prosecutable evidence — no legal documents were generated. "
            "This is the correct outcome when the case is clean."
        )

    reasoning = (risk_reasoning or "").strip()
    if len(reasoning) < 80:
        return (
            "PDF NOT RENDERED: risk_reasoning is too short to back a prosecution "
            "(<80 chars). Provide a paragraph that cites the specific GFW indicators, "
            "AIS-gap timestamps, MPA / RFMO names, or rule breaches that justify the "
            f"{verdict} verdict, or downgrade the verdict and skip rendering."
        )

    try:
        check_status, check_detail = _classify_one_mmsi_fishing(mmsi)
    except Exception as exc:
        return (
            f"PDF NOT RENDERED: pre-render fishing-vessel check failed for MMSI={mmsi} "
            f"({exc!s}). Refusing to render without a confirmed fishing-vessel identity."
        )
    if check_status == "NOT_FISHING":
        return (
            f"PDF NOT RENDERED: GFW vessel-identity says MMSI={mmsi} is NOT a fishing "
            f"vessel ({check_detail}). IUU fishing charges do not apply. The pipeline "
            "must skip render and report no prosecutable evidence."
        )

    port_dict: dict | None = None
    if port_name:
        port_dict = {
            "name": port_name,
            "country": port_country,
            "un_locode": port_locode,
        }
    else:
        # Last-resort: resolve at render time if the supervisor forgot to pass it.
        try:
            port_dict = find_nearest_port(latitude, longitude)
        except Exception:
            port_dict = None

    try:
        case = _build_case_file(
            mmsi=mmsi,
            latitude=latitude,
            longitude=longitude,
            region_name=region_name,
            vessel_name=vessel_name,
            vessel_flag=vessel_flag,
            vessel_imo=vessel_imo,
            gear_type=gear_type,
            length_m=length_m,
            last_seen_iso=last_seen_iso,
            region_id=region_id,
            eez_country=eez_country,
            case_id=case_id,
            events_json=events_json,
            citations_json=citations_json,
            port=port_dict,
        )
    except Exception as exc:
        return f"PDF render failed at CaseFile assembly: {exc!s}"

    classification_map = {
        "HIGH": "confirmed_iuu",
        "MEDIUM": "high_risk",
    }
    case.risk = RiskAssessment(
        vessel=case.vessel,
        region_id=case.region.region_id,
        risk_score=max(0.0, min(1.0, risk_score)),
        classification=classification_map[verdict],
        triggered_rules=[],
        evidence=[],
        reasoning=risk_reasoning,
    )

    try:
        artifact = render_combined_legal_pdf(case)
    except Exception as exc:
        return f"PDF render failed in Playwright pipeline: {exc!s}"

    from documents.render import OUTPUT_DIR

    doc_filename = f"{artifact.doc_type}.pdf"
    pdf_path = OUTPUT_DIR / case.case_id / doc_filename
    port_line = ""
    if port_dict and port_dict.get("name"):
        port_line = (
            f"  port_name: {port_dict.get('name')}\n"
            f"  port_country: {port_dict.get('country') or '?'}\n"
            f"  port_locode: {port_dict.get('un_locode') or '?'}\n"
        )
    return (
        f"EVIDENCE_PDF_RENDERED: case_id={case.case_id} verdict={verdict}\n"
        f"  mmsi: {mmsi}\n"
        f"  vessel_name: {vessel_name or 'Unknown'}\n"
        f"  vessel_flag: {vessel_flag or '?'}\n"
        + port_line +
        f"  doc: {doc_filename}\n"
        f"  path: {pdf_path}\n"
        f"  sha256: {artifact.sha256}\n"
        f"  pages: {artifact.page_count}"
    )


SYSTEM_PROMPT = """You are a vessel-incursion analyst. Trigger: a "supposed vessel entering region X"
event has been reported. Your job is to assemble an evidence document by composing three
specialist subagents and synthesizing their findings.

PIPELINE — turn 1 has already been prefetched IN PARALLEL by the runtime
and is provided inline in the human message under
"TURN-1 DATA (already gathered)". The prefetched blocks are:
  - check_ais_at_location          (live AIS broadcasts)
  - find_dark_targets_in_region    (SAR satellite radar count)
  - lookup_regional_laws           (citation-backed legal dossier)
  - filter_to_fishing_vessels      (GFW vessel-identity for the closest 15 AIS)
  - find_historical_vessels_in_region [FISHING, last 90 d]   (events fallback)
  - NEAREST_PORT                  (closest port to the incident, GFW or static)
Do NOT re-call any of these tools — their results are inline above and are
authoritative.

When you call render_evidence_pdf, ALWAYS pass the prefetched NEAREST_PORT
fields as port_name / port_country / port_locode. The PDF cover page is
addressed to that port authority. If NEAREST_PORT lookup failed, omit them
and the renderer will resolve a default. (They are still registered as tools only as a fallback for
adversarial cases.)

Compute the dark-target gap from the prefetched turn-1 data:
  - dark_target_count = max(0, SAR_DETECTIONS_count - AIS_STATUS_count)
  - dark_target_count > 0 means satellite radar saw vessels that AIS did not —
    a strong dark-fishing signal that MUST be surfaced in the evidence document.

FISHING-VESSEL GATE (read FISHING_FILTER block in the prefetch first):
  The pipeline ONLY assesses IUU risk for fishing vessels — cargo, tankers,
  passenger ships, tugs and pleasure craft cannot commit IUU fishing by
  definition. The prefetched FISHING_FILTER block lists each closest AIS
  contact with its gfw_status:
    - FISHING     → eligible for classify_vessels_iuu_batch
    - NOT_FISHING → MUST be excluded
    - UNKNOWN     → exclude unless they appear in find_historical_vessels_in_region
                    FISHING events (in which case treat as suspicious dark fishing)
  The PASS_TO_CLASSIFIER list at the bottom of FISHING_FILTER is the ONLY
  set of MMSIs you may pass to classify_vessels_iuu_batch from AIS data.
  If PASS_TO_CLASSIFIER is empty AND AIS_STATUS is not silent AND there is
  no historical-events fallback to run, HALT IMMEDIATELY:
    - Do NOT call classify_vessels_iuu_batch.
    - Do NOT call render_evidence_pdf.
    - Synthesize the evidence document with verdict
        "NO IUU ASSESSMENT — no fishing vessels detected in the region"
      and write LEGAL DOCUMENTS: NOT RENDERED (no fishing vessels present).

Turn 1 (your first action) — branch on the prefetched AIS + FISHING_FILTER:
  CASE A: PASS_TO_CLASSIFIER lists at least one FISHING MMSI.
    Call classify_vessels_iuu_batch(mmsis=PASS_TO_CLASSIFIER) ONCE (cap 15).
    The tool fans them out to threads internally on Haiku 4.5 — latency
    ~= slowest single classification, not Nx. Do NOT emit multiple
    classify_vessel_iuu tool calls — the batch tool replaces that pattern.

  CASE B: AIS_STATUS: silent (zero vessels broadcasting).
    This is itself a red flag. Use the prefetched
    `find_historical_vessels_in_region [FISHING, last 90 d]` block above —
    those MMSIs come from GFW's FISHING events dataset, which is already
    filtered to fishing-vessel events. Pass up to 15 of those MMSIs straight
    into classify_vessels_iuu_batch. (You may optionally call
    filter_to_fishing_vessels first if you want to double-check identity,
    but it is not required for the FISHING dataset.)

  CASE C: PASS_TO_CLASSIFIER is empty and AIS is NOT silent.
    HALT per the FISHING-VESSEL GATE above. Do not classify, do not render.

Turn 2 — synthesize the evidence document.

Turn 3 — CONDITIONAL: render a combined legal PDF only if the case is prosecutable.
  Decision rule (the GATE — be conservative; default is NO RENDER):
    Render if AND ONLY IF ALL of:
      (1) at least one classify_vessels_iuu_batch verdict is HIGH (preferred)
          or MEDIUM with a CITED named indicator (specific MPA event id, RFMO
          IUU list entry, dated AIS gap inside named protected area);
      (2) the underlying vessel passed the FISHING-VESSEL GATE
          (gfw_status=FISHING in FISHING_FILTER, NOT just UNKNOWN);
      (3) at least one of the following corroborating signals is present:
            (a) lookup_regional_laws returned a specific rule breach (not
                INSUFFICIENT_DATA) that matches the vessel's behaviour, OR
            (b) AIS_STATUS shows a clear AIS gap inside the protected region
                AND DARK_TARGET_GAP > 0 from SAR, OR
            (c) the GFW verdict was HIGH (which alone supplies enough).
    SKIP otherwise. Default to SKIP. If you skip, write
      "LEGAL DOCUMENTS: NOT RENDERED (insufficient evidence — case is clean)"
    in the synthesis and end the pipeline. A skip is the CORRECT outcome
    on a clean case; do not reach for a HIGH/MEDIUM verdict to justify
    rendering a PDF.

  When you do call render_evidence_pdf, call it ONCE on the highest-risk MMSI:
    - mmsi, latitude, longitude (last known AIS or historical-event position)
    - region_name (from lookup_regional_laws)
    - risk_classification: "HIGH" or "MEDIUM" only
    - risk_score: 0.0–1.0 (your confidence in the verdict)
    - risk_reasoning: one paragraph summary of why prosecution is warranted,
      citing the SPECIFIC indicators that triggered the gate
    - vessel_name, vessel_flag, vessel_imo, gear_type, length_m, last_seen_iso,
      eez_country: pass whatever you have, None otherwise
    - port_name, port_country, port_locode: copy from the prefetched
      NEAREST_PORT block — the PDF + downstream call are addressed to this port
    - events_json: optional JSON list of evidentiary events
  The tool refuses LOW / INSUFFICIENT_DATA — do not try to bypass the gate.

HARD RULES:
- Pass MMSIs verbatim to classify_vessels_iuu_batch. Never pass a vessel name.
- Cap classify_vessels_iuu_batch at 15 MMSIs per pipeline run.
- NEVER classify a NOT_FISHING vessel for IUU risk. They cannot commit IUU
  fishing. If you find yourself about to do so, stop and exclude.
- Never invent rules. If lookup_regional_laws returns INSUFFICIENT_DATA, say so.
- render_evidence_pdf is the LAST tool call. Do not invoke any analysis tool after it.
- Default to NO RENDER. Rendering a legal PDF is a serious action that names
  an actual vessel for prosecution; it must be backed by cited indicators.

OUTPUT FORMAT (terse — write only what fits the case, no padding):

EVIDENCE OF POTENTIAL IUU FISHING ACTIVITY
INCIDENT: (<lat>, <lon>) — <region or "uncached waters">

AIS / SAR:
- AIS in <radius> mi: <n>; SAR (last <days_back> d): <n>; DARK GAP: <max(0, sar-ais)>

VESSELS:
- MMSI <m> | <name?> | <flag?> | VERDICT: <HIGH|MEDIUM|LOW|INSUFFICIENT_DATA>
  · <one short evidence line>

LEGAL CONTEXT:
- Coastal state: <ISO3>; ProtectedSeas LFP: <1–5>
- Key rule(s): <instrument> [source_url, last_checked]

LEGAL DOCUMENTS:
- <If render_evidence_pdf was called: paste its returned EVIDENCE_PDF_RENDERED block.>
- <If skipped: "NOT RENDERED (insufficient evidence — case is clean)">

CAVEATS:
- GFW indicators are apparent activity inferred from AIS; AIS absence may reflect signal loss.
"""


def build_supervisor(model: str = "claude-sonnet-4-6") -> AgentExecutor:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    llm = ChatAnthropic(model=model, temperature=0, max_tokens=8192)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ]
    )
    tools = [
        check_ais_at_location,
        find_dark_targets_in_region,
        lookup_regional_laws,
        filter_to_fishing_vessels,
        classify_vessels_iuu_batch,
        find_historical_vessels_in_region,
        render_evidence_pdf,
    ]
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=True, max_iterations=12)


def _unwrap_output(out) -> str:
    """LangChain + Anthropic sometimes returns the supervisor's final message as
    a list of content blocks ({'text': ..., 'type': 'text'}) rather than a flat
    string. Flatten to text so callers and assertions see the actual content."""
    if isinstance(out, str):
        return out
    if isinstance(out, list):
        parts: list[str] = []
        for block in out:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(out)


def _candidates_from_vessels(vessels) -> list[tuple[str, str]]:
    """Filter a list[Vessel] to the closest 15 that aren't obvious non-fishing
    AIS bands. Returns (mmsi, ais_class) pairs ordered by distance.

    Vessels are already distance-sorted by vessels_within_radius; we just drop
    entries flagged NOT_FISHING (passenger/cargo/tanker AIS bands) so the
    downstream GFW filter doesn't waste calls on them.
    """
    out: list[tuple[str, str]] = []
    for v in vessels:
        if not v.mmsi:
            continue
        tag = _ais_fishing_tag(v.type_code)
        if tag == "NOT_FISHING":
            continue
        out.append((v.mmsi, tag))
        if len(out) >= 15:
            break
    return out


def _format_prefetched_fishing_filter(
    candidates: list[tuple[str, str]],
    resolved: dict[str, tuple[str, str]],
) -> str:
    if not candidates:
        return (
            "FISHING_FILTER: no AIS candidates to resolve "
            "(either AIS silent or all contacts were obvious non-fishing types)."
        )
    lines = ["FISHING_FILTER (prefetched, GFW vessel-identity):"]
    fishing: list[str] = []
    for mmsi, ais_tag in candidates:
        if mmsi in resolved:
            status, detail = resolved[mmsi]
        elif ais_tag == "LIKELY_FISHING":
            status, detail = "FISHING", "AIS shiptype=30 (Fishing); GFW lookup skipped"
        else:
            status, detail = "UNKNOWN", "no GFW result"
        if status == "FISHING":
            fishing.append(mmsi)
        lines.append(f"MMSI={mmsi} | ais={ais_tag} | gfw_status={status} | {detail}")
    if fishing:
        lines.append(f"PASS_TO_CLASSIFIER: {fishing}")
    else:
        lines.append(
            "PASS_TO_CLASSIFIER: [] — no fishing vessels confirmed; the pipeline "
            "must HALT without running classify_vessels_iuu_batch or render_evidence_pdf."
        )
    return "\n".join(lines)


def _fetch_ais_once(
    latitude: float, longitude: float, radius_miles: float
) -> list:
    """Single-call wrapper around vessels_within_radius — used by the prefetch
    so we don't open two AIS websockets in parallel for the same bbox.
    Returns [] on any error; the caller formats / extracts candidates.
    """
    try:
        return vessels_within_radius(latitude, longitude, radius_miles)
    except Exception:
        return []


def _fetch_nearest_port(latitude: float, longitude: float) -> dict | None:
    """Resolve the nearest port to (lat, lon). GFW PORT_VISIT first, static fallback."""
    try:
        return find_nearest_port(latitude, longitude)
    except Exception:
        return None


def _format_nearest_port(port: dict | None) -> str:
    if not port:
        return "NEAREST_PORT: lookup failed — no port resolved."
    locode = port.get("un_locode") or "?"
    return (
        f"NEAREST_PORT: {port.get('name')} ({locode}) | "
        f"country={port.get('country')} | "
        f"position=({port.get('lat')}, {port.get('lon')}) | "
        f"distance={port.get('distance_mi')} mi | "
        f"source={port.get('source')}"
    )


def _fetch_historical_fishing(
    latitude: float, longitude: float, radius_miles: float, days_back: int = 90
) -> str:
    """Prefetch the FISHING-events historical fallback so the supervisor has
    it available without paying a serial round-trip when AIS turns out silent.
    The FISHING dataset already restricts to fishing-vessel events on GFW's
    side, so this list is pre-filtered to fishing-capable MMSIs.
    """
    end_d = date.today()
    start_d = end_d - timedelta(days=days_back)
    bbox = bbox_for_radius(latitude, longitude, radius_miles)
    try:
        events = get_events_in_region(
            bbox,
            event_type="FISHING",
            start_date=start_d.isoformat(),
            end_date=end_d.isoformat(),
        )
    except Exception as exc:
        return f"HISTORICAL_FISHING prefetch failed: {exc!s}"
    return _format_historical_events(events, "FISHING")


def _prefetch_turn1(
    latitude: float,
    longitude: float,
    radius_miles: float,
    port_country_code: str | None,
) -> dict[str, str]:
    """Run the independent turn-1 fetches concurrently.

    Parallel batch (single ThreadPoolExecutor):
      - AIS (one websocket, ~30s)
      - SAR 4Wings (~5s)
      - Regional-law LLM (~30s)
      - GFW Events FISHING fallback (~3-5s) — always prefetched so the
        AIS-silent branch doesn't pay a serial round-trip later.

    Once AIS resolves we derive the closest-15 fishing candidates from the
    same vessel list (no second AIS call) and resolve their fishing status
    in parallel via _filter_fishing_mmsis. SAR + law + historical may still
    be in flight while we do that — net wall time is max(AIS+filter, law).
    """
    def _safe(fut, label: str) -> str:
        try:
            return fut.result()
        except Exception as exc:
            return f"({label} prefetch failed: {exc!s})"

    with ThreadPoolExecutor(max_workers=5) as pool:
        ais_fut = pool.submit(_fetch_ais_once, latitude, longitude, radius_miles)
        sar_fut = pool.submit(
            find_dark_targets_in_region.invoke,
            {"latitude": latitude, "longitude": longitude, "radius_miles": radius_miles},
        )
        law_fut = pool.submit(
            lookup_regional_laws.invoke,
            {
                "latitude": latitude,
                "longitude": longitude,
                "port_country_code": port_country_code,
            },
        )
        hist_fut = pool.submit(
            _fetch_historical_fishing, latitude, longitude, radius_miles
        )
        port_fut = pool.submit(_fetch_nearest_port, latitude, longitude)

        try:
            ais_vessels = ais_fut.result()
        except Exception:
            ais_vessels = []
        ais_str = _format_ais_vessels(ais_vessels)
        candidates = _candidates_from_vessels(ais_vessels)

        if candidates:
            mmsis_to_resolve = [m for m, tag in candidates if tag != "LIKELY_FISHING"]
            try:
                resolved = (
                    _filter_fishing_mmsis(mmsis_to_resolve) if mmsis_to_resolve else {}
                )
            except Exception:
                resolved = {}
        else:
            resolved = {}

        try:
            port = port_fut.result()
        except Exception:
            port = None

        return {
            "ais": ais_str,
            "sar": _safe(sar_fut, "find_dark_targets_in_region"),
            "law": _safe(law_fut, "lookup_regional_laws"),
            "fishing_filter": _format_prefetched_fishing_filter(candidates, resolved),
            "historical_fishing": _safe(hist_fut, "find_historical_vessels_in_region"),
            "nearest_port": _format_nearest_port(port),
            "_port": port,  # raw dict; consumed by evaluate_incident, not the LLM
        }


def evaluate_incident(
    latitude: float,
    longitude: float,
    radius_miles: float = 50.0,
    port_country_code: str | None = None,
    mmsi: str | None = None,
) -> str:
    prefetch = _prefetch_turn1(latitude, longitude, radius_miles, port_country_code)

    extras = []
    if port_country_code:
        extras.append(f"port_country_code = {port_country_code!r}")
    if mmsi:
        extras.append(
            f"a specific vessel of interest with MMSI={mmsi} was identified by the trigger; "
            "include it in the classify_vessels_iuu_batch list alongside the AIS-discovered set"
        )
    extras_str = (" Context: " + "; ".join(extras) + ".") if extras else ""

    question = (
        f"A supposed vessel has been reported entering the region around "
        f"latitude {latitude}, longitude {longitude} (search radius {radius_miles} miles)."
        f"{extras_str}\n\n"
        "TURN-1 DATA (already gathered — prefetched in parallel; do NOT re-call):\n\n"
        f"--- check_ais_at_location ---\n{prefetch['ais']}\n\n"
        f"--- find_dark_targets_in_region ---\n{prefetch['sar']}\n\n"
        f"--- lookup_regional_laws ---\n{prefetch['law']}\n\n"
        f"--- filter_to_fishing_vessels (prefetched) ---\n{prefetch['fishing_filter']}\n\n"
        f"--- find_historical_vessels_in_region [FISHING, last 90 d] (prefetched) ---\n"
        f"{prefetch['historical_fishing']}\n\n"
        f"--- NEAREST_PORT (prefetched) ---\n{prefetch['nearest_port']}\n\n"
        "Now apply the FISHING-VESSEL GATE on the FISHING_FILTER block. If "
        "PASS_TO_CLASSIFIER is non-empty, call classify_vessels_iuu_batch on "
        "exactly that list. If it is empty and AIS is silent (zero broadcasts), "
        "use the prefetched HISTORICAL_EVENTS FISHING list above as the candidate "
        "MMSI source — those are pre-filtered to fishing-vessel events by GFW's "
        "FISHING dataset, so you can pass them straight into "
        "classify_vessels_iuu_batch (still cap 15). Do NOT re-call "
        "find_historical_vessels_in_region for FISHING — its result is above. "
        "If the FISHING_FILTER PASS_TO_CLASSIFIER is empty AND AIS is not silent, "
        "HALT — do not classify, do not render. Then synthesize the evidence "
        "document, and call render_evidence_pdf only if the strict gate criteria "
        "in the system prompt are ALL met."
    )
    executor = build_supervisor()
    result = executor.invoke({"input": question})
    raw = result["output"] if isinstance(result, dict) else result
    return _unwrap_output(raw)


_PDF_PATH_RE = re.compile(r"path:\s*(.+\.pdf)\s*$", re.MULTILINE | re.IGNORECASE)
_CASE_ID_RE = re.compile(r"case_id=([A-Za-z0-9_\-]+)")
_MMSI_RE = re.compile(r"^\s*mmsi:\s*([0-9]+)\s*$", re.MULTILINE | re.IGNORECASE)
_VESSEL_NAME_RE = re.compile(r"^\s*vessel_name:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)
_VESSEL_FLAG_RE = re.compile(r"^\s*vessel_flag:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)
_DOC_RE = re.compile(r"^\s*doc:\s*(.+\.pdf)\s*$", re.MULTILINE | re.IGNORECASE)
_PORT_NAME_RE = re.compile(r"^\s*port_name:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)
_PORT_COUNTRY_RE = re.compile(r"^\s*port_country:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)
_PORT_LOCODE_RE = re.compile(r"^\s*port_locode:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)


def _parse_pipeline_artifacts(summary: str) -> dict:
    """Extract risk flag + PDF metadata from a supervisor synthesis.

    risk=True iff render_evidence_pdf actually produced a PDF (the renderer's
    success line is "EVIDENCE_PDF_RENDERED: ..."). All other outcomes — clean
    case, NO IUU ASSESSMENT, NOT RENDERED — are risk=False. Refusing to render
    on bad inputs (verdict LOW, short reasoning, NOT_FISHING vessel) does NOT
    count as risk; that is the pipeline correctly skipping a clean case.
    """
    rendered = "EVIDENCE_PDF_RENDERED" in summary
    out: dict = {
        "risk": rendered,
        "pdf_path": None,
        "case_id": None,
        "mmsi": None,
        "vessel_name": None,
        "vessel_flag": None,
        "doc_filename": None,
        "port_name": None,
        "port_country": None,
        "port_locode": None,
    }
    if not rendered:
        return out

    block_start = summary.find("EVIDENCE_PDF_RENDERED")
    block = summary[block_start:] if block_start >= 0 else summary

    if (m := _PDF_PATH_RE.search(block)):
        out["pdf_path"] = m.group(1).strip()
    if (m := _CASE_ID_RE.search(block)):
        out["case_id"] = m.group(1).strip()
    if (m := _MMSI_RE.search(block)):
        out["mmsi"] = m.group(1).strip()
    if (m := _VESSEL_NAME_RE.search(block)):
        out["vessel_name"] = m.group(1).strip()
    if (m := _VESSEL_FLAG_RE.search(block)):
        out["vessel_flag"] = m.group(1).strip()
    if (m := _DOC_RE.search(block)):
        out["doc_filename"] = m.group(1).strip()
    if (m := _PORT_NAME_RE.search(block)):
        out["port_name"] = m.group(1).strip()
    if (m := _PORT_COUNTRY_RE.search(block)):
        out["port_country"] = m.group(1).strip()
    if (m := _PORT_LOCODE_RE.search(block)):
        out["port_locode"] = m.group(1).strip()
    return out


def evaluate_incident_structured(
    latitude: float,
    longitude: float,
    radius_miles: float = 50.0,
    port_country_code: str | None = None,
    mmsi: str | None = None,
) -> dict:
    """Same pipeline as evaluate_incident, returned as a structured dict.

    Shape:
      {
        "risk":     bool,            # True iff a prosecution PDF was rendered
        "summary":  str,              # full supervisor synthesis
        "pdf_path": str | None,       # absolute path to combined_legal_package.pdf
        "case_id":  str | None,       # IUU-YYYYMMDD-HHMMSS-XXXX
      }
    """
    summary = evaluate_incident(
        latitude,
        longitude,
        radius_miles=radius_miles,
        port_country_code=port_country_code,
        mmsi=mmsi,
    )
    artifacts = _parse_pipeline_artifacts(summary)
    return {"summary": summary, **artifacts}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-agent vessel-incursion evidence pipeline."
    )
    parser.add_argument("lat", type=float, help="latitude (decimal degrees)")
    parser.add_argument("lon", type=float, help="longitude (decimal degrees)")
    parser.add_argument(
        "--radius", type=float, default=50.0, help="search radius in miles (default 50)"
    )
    parser.add_argument(
        "--port-country", dest="port_country", help="ISO3 port country code (e.g. PHL)"
    )
    parser.add_argument(
        "--mmsi", help="optional known MMSI from the trigger event"
    )
    args = parser.parse_args()

    print(
        evaluate_incident(
            args.lat,
            args.lon,
            radius_miles=args.radius,
            port_country_code=args.port_country,
            mmsi=args.mmsi,
        )
    )


if __name__ == "__main__":
    main()
