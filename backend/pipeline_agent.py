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
    get_events_in_region,
    get_sar_detections_in_region,
    sar_detection_count,
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
from vessel_lookup import bbox_for_radius, vessels_within_radius

load_dotenv()


def _format_ais_vessels(vessels) -> str:
    if not vessels:
        return "AIS_STATUS: silent — no vessels broadcasting AIS in the queried window."
    lines = [f"AIS_STATUS: {len(vessels)} vessel(s) broadcasting AIS, ordered by distance:"]
    for v in vessels:
        mmsi = v.mmsi or "unknown"
        lines.append(
            f"MMSI={mmsi} | name={v.name!r} | ship_type={v.type or '?'} | "
            f"position=({v.latitude:.4f}, {v.longitude:.4f}) | distance={v.distance_miles:.1f} mi"
        )
    return "\n".join(lines)


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
    )[:6]

    if not ranked:
        return f"HISTORICAL_EVENTS: {len(events)} {event_type} events but none carry an MMSI."

    lines = [
        f"HISTORICAL_EVENTS: {len(events)} {event_type} event(s) from "
        f"{len(seen)} unique MMSI(s); top 6 most recent:"
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
    """Classify up to 6 MMSIs in parallel via threads. Pass 9-digit MMSIs verbatim
    from check_ais_at_location or find_historical_vessels_in_region.

    HARD RULE: never pass vessel names. MMSI only (9-digit) or IMO (7-digit)
    as fallback. GFW search fuzzy-matches names and selects the wrong vessel.

    Total latency ~= slowest single classification (~30-60 s) instead of N x.
    Capped at 6 MMSIs at the code level. Returns one block per MMSI separated
    by `=== MMSI <m> ===` headers, in the order they were submitted.
    """
    cleaned = [m.strip() for m in mmsis if m and m.strip()][:6]
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
    return CaseFile(
        case_id=cid,
        region=region,
        vessel=vessel,
        events=events,
        rules=[],
        citations=citations,
        fine=fine,
        risk=risk,
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

    pdf_path = OUTPUT_DIR / case.case_id / f"{artifact.doc_type}.pdf"
    return (
        f"EVIDENCE_PDF_RENDERED: case_id={case.case_id} verdict={verdict}\n"
        f"  path: {pdf_path}\n"
        f"  sha256: {artifact.sha256}\n"
        f"  pages: {artifact.page_count}"
    )


SYSTEM_PROMPT = """You are a vessel-incursion analyst. Trigger: a "supposed vessel entering region X"
event has been reported. Your job is to assemble an evidence document by composing three
specialist subagents and synthesizing their findings.

PIPELINE — turn 1 has already been prefetched IN PARALLEL by the runtime
and is provided inline in the human message under
"TURN-1 DATA (already gathered)". Do NOT re-call check_ais_at_location,
find_dark_targets_in_region, or lookup_regional_laws — their results are
above. (They are still registered as tools only as a fallback; assume the
prefetched data is authoritative.)

Compute the dark-target gap from the prefetched turn-1 data:
  - dark_target_count = max(0, SAR_DETECTIONS_count - AIS_STATUS_count)
  - dark_target_count > 0 means satellite radar saw vessels that AIS did not —
    a strong dark-fishing signal that MUST be surfaced in the evidence document.

Turn 1 (your first action) — branch on the prefetched AIS result:
  CASE A: check_ais_at_location output lists MMSIs.
    Pick the top 6 closest (already distance-ordered). Call
    classify_vessels_iuu_batch(mmsis=[<m1>, ..., <m6>]) ONCE with the list.
    The tool fans them out to threads internally — latency ~= slowest
    single classification, not 6x. Do NOT emit multiple classify_vessel_iuu
    tool calls — the batch tool replaces that pattern.

  CASE B: AIS_STATUS: silent (zero vessels broadcasting).
    This is itself a red flag. Call find_historical_vessels_in_region(...).
    Then call classify_vessels_iuu_batch(mmsis=[<...>]) ONCE with the top 6
    MMSIs returned. Same threading semantics as CASE A.

Turn 2 — synthesize the evidence document.

Turn 3 — CONDITIONAL: render a combined legal PDF only if the case is prosecutable.
  Decision rule (the GATE):
    Render if ANY of:
      (a) at least one classify_vessels_iuu_batch verdict is HIGH or MEDIUM, OR
      (b) AIS_STATUS shows a clear AIS gap inside the protected region AND
          DARK_TARGET_GAP > 0 from SAR, OR
      (c) lookup_regional_laws returned a confirmed rule breach (not
          INSUFFICIENT_DATA) tied to a specific vessel's behaviour.
    SKIP otherwise. If you skip, write
      "LEGAL DOCUMENTS: NOT RENDERED (insufficient evidence — case is clean)"
    in the synthesis and end the pipeline.

  When you do call render_evidence_pdf, call it ONCE on the highest-risk MMSI:
    - mmsi, latitude, longitude (last known AIS or historical-event position)
    - region_name (from lookup_regional_laws)
    - risk_classification: "HIGH" or "MEDIUM" only
    - risk_score: 0.0–1.0 (your confidence in the verdict)
    - risk_reasoning: one paragraph summary of why prosecution is warranted
    - vessel_name, vessel_flag, vessel_imo, gear_type, length_m, last_seen_iso,
      eez_country: pass whatever you have, None otherwise
    - events_json: optional JSON list of evidentiary events
  The tool refuses LOW / INSUFFICIENT_DATA — do not try to bypass the gate.

HARD RULES:
- Pass MMSIs verbatim to classify_vessels_iuu_batch. Never pass a vessel name.
- Cap classify_vessels_iuu_batch at 6 MMSIs per pipeline run.
- Never invent rules. If lookup_regional_laws returns INSUFFICIENT_DATA, say so.
- render_evidence_pdf is the LAST tool call. Do not invoke any analysis tool after it.

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


def _prefetch_turn1(
    latitude: float,
    longitude: float,
    radius_miles: float,
    port_country_code: str | None,
) -> dict[str, str]:
    """Run the three independent turn-1 fetches concurrently.

    LangChain's AgentExecutor runs tool calls serially even when the model
    emits them in a single parallel response, so the supervisor would pay
    ~30s (AIS) + ~5s (SAR) + ~30s (legal LLM) sequentially. AIS, SAR, and
    legal-dossier hit completely independent backends — fan them out to a
    ThreadPoolExecutor so wall time is max() instead of sum().
    """
    def _safe(fut, label: str) -> str:
        try:
            return fut.result()
        except Exception as exc:
            return f"({label} prefetch failed: {exc!s})"

    with ThreadPoolExecutor(max_workers=3) as pool:
        ais_fut = pool.submit(
            check_ais_at_location.invoke,
            {"latitude": latitude, "longitude": longitude, "radius_miles": radius_miles},
        )
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
        return {
            "ais": _safe(ais_fut, "check_ais_at_location"),
            "sar": _safe(sar_fut, "find_dark_targets_in_region"),
            "law": _safe(law_fut, "lookup_regional_laws"),
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
        "Now: classify_vessels_iuu_batch on the top 6 MMSIs (or call "
        "find_historical_vessels_in_region first if AIS is silent), "
        "synthesize the evidence document, and call render_evidence_pdf "
        "if the gate criteria are met."
    )
    executor = build_supervisor()
    result = executor.invoke({"input": question})
    raw = result["output"] if isinstance(result, dict) else result
    return _unwrap_output(raw)


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
