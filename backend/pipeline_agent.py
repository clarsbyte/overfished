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
import os
from datetime import date, timedelta

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


SYSTEM_PROMPT = """You are a vessel-incursion analyst. Trigger: a "supposed vessel entering region X"
event has been reported. Your job is to assemble an evidence document by composing three
specialist subagents and synthesizing their findings.

PIPELINE — follow this order strictly:

Turn 1 (call ALL THREE tools in the same response — they are independent):
  - check_ais_at_location(latitude, longitude, radius_miles)
  - find_dark_targets_in_region(latitude, longitude, radius_miles)
  - lookup_regional_laws(latitude, longitude, port_country_code=...)

Compute the dark-target gap from turn 1's results:
  - dark_target_count = max(0, SAR_DETECTIONS_count - AIS_STATUS_count)
  - dark_target_count > 0 means satellite radar saw vessels that AIS did not —
    a strong dark-fishing signal that MUST be surfaced in the evidence document.

Turn 2 — branch on AIS results:
  CASE A: check_ais_at_location returned MMSIs.
    Pick the top 6 closest (the AIS output is already distance-ordered).
    Call classify_vessel_iuu(mmsi=<...>) ONCE PER MMSI in a single turn so
    they execute in parallel.

  CASE B: AIS_STATUS: silent (zero vessels broadcasting).
    This is itself a red flag. Call find_historical_vessels_in_region(...).
    Then call classify_vessel_iuu(mmsi=<...>) for the top 6 MMSIs returned,
    again in parallel in one turn.

Turn 3 — synthesize the evidence document.

HARD RULES:
- Pass MMSIs verbatim to classify_vessel_iuu. Never pass a vessel name; GFW
  search fuzzy-matches names and returns wrong vessels.
- Cap classify_vessel_iuu calls at 6 per pipeline run.
- Never invent rules. If lookup_regional_laws returns INSUFFICIENT_DATA, say so.
- Every legal claim in the synthesis must cite source_url + last_checked from
  the regional dossier output.

OUTPUT FORMAT (return exactly this structure as your final message):

EVIDENCE OF POTENTIAL IUU FISHING ACTIVITY
==========================================
INCIDENT LOCATION: (<lat>, <lon>) — <region name or "uncached coastal waters">
ASSEMBLED AT: <UTC timestamp>

AIS STATUS AT LOCATION:
- Vessels broadcasting AIS in <radius> mi: <ais_count>
- SAR-detected vessels (Sentinel-1 satellite, last <days_back> d): <sar_count>
- DARK TARGET GAP: <max(0, sar_count - ais_count)> vessels visible to SAR but
  not broadcasting AIS. <If > 0, mark as RED FLAG and call out explicitly.>
- [If AIS silent]: NO AIS activity detected — possible AIS evasion (red flag).

VESSELS INVESTIGATED:
1. <name> (MMSI <...>, flag <...>, GFW vessel_id <...>)
   IUU VERDICT: <HIGH | MEDIUM | LOW | INSUFFICIENT_DATA>
   Evidence:
   - <key bullets pulled from classify_vessel_iuu output>
2. ...

LEGAL CONTEXT:
- Coastal state: <country>
- Protection level (ProtectedSeas LFP): <1–5> — <interpretation>
- Key applicable rules:
  - <rule> [FAOLEX/FISHLEX, source_url, last_checked]
  - ...

LAWS POTENTIALLY BREACHED (per vessel):
- <vessel name> (MMSI <...>) may breach: <rule> — <citation> [source_url, last_checked]

PENALTIES (FISHLEX):
- <quote from coastal_state.fishlex.fields.penalties> [source_url, last_checked]

RECOMMENDED ACTIONS:
- Notify competent authority: <jurisdiction>
- Port denial grounds applicable: <quote from portlex.fields.denial_grounds>
- Required documents to demand on inspection: <list from portlex.fields.required_documents>
- Inspection priority items: <bullets>

SOURCES:
- AIS: AISStream.io (live)
- Vessel history: Global Fishing Watch Insights/Events/Vessels APIs
- Geospatial: ProtectedSeas Navigator (live)
- Regional law: <FAOLEX/FISHLEX/PORTLEX URLs with last_checked dates>

CAVEATS:
- GFW indicators reflect "apparent" activity inferred from AIS, not adjudicated illegal fishing.
- Regional rules sourced from curated FAO database cache (confidence: curated).
- AIS absence is suggestive of AIS-off behavior but not conclusive — may also reflect signal loss.
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
        classify_vessel_iuu,
        find_historical_vessels_in_region,
    ]
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=True, max_iterations=8)


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


def evaluate_incident(
    latitude: float,
    longitude: float,
    radius_miles: float = 50.0,
    port_country_code: str | None = None,
    mmsi: str | None = None,
) -> str:
    executor = build_supervisor()
    extras = []
    if port_country_code:
        extras.append(f"port_country_code = {port_country_code!r}")
    if mmsi:
        extras.append(
            f"a specific vessel of interest with MMSI={mmsi} was identified by the trigger; "
            "you may classify it directly via classify_vessel_iuu in addition to the AIS-discovered set"
        )
    extras_str = (" Context: " + "; ".join(extras) + ".") if extras else ""
    question = (
        f"A supposed vessel has been reported entering the region around "
        f"latitude {latitude}, longitude {longitude} (search radius {radius_miles} miles). "
        f"Run the pipeline and return the formatted evidence document.{extras_str}"
    )
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
