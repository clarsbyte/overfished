"""LangChain agent that classifies a vessel's IUU fishing risk using GFW data.

Run as a CLI:
    python gfw_agent.py <mmsi_imo_or_name> [days_back]

Or import:
    from gfw_agent import classify_vessel
    print(classify_vessel("273435360"))
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta

from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from gfw_lookup import (
    VesselRecord,
    get_vessel_events,
    get_vessel_insights,
    pick_best_vessel,
    search_vessel,
)

load_dotenv()


def _format_vessel(v: VesselRecord) -> str:
    auth_brief = (
        "; ".join(
            f"{a.get('sourceCode', '?')}={a.get('isAuthorized', '?')}"
            for a in v.authorizations[:6]
        )
        or "(none on record)"
    )
    owner_brief = (
        "; ".join(
            f"{o.get('name', '?')} ({o.get('flag', '?')})" for o in v.owners[:3]
        )
        or "(none on record)"
    )
    return (
        f"vessel_id: {v.vessel_id}\n"
        f"name: {v.name or 'Unknown'}\n"
        f"mmsi: {v.mmsi}  imo: {v.imo}  callsign: {v.callsign}\n"
        f"flag: {v.flag}  ship_type: {v.ship_type}  gear_type: {v.gear_type}\n"
        f"owners ({len(v.owners)}): {owner_brief}\n"
        f"authorizations ({len(v.authorizations)}): {auth_brief}"
    )


def _format_insights(payload: dict) -> str:
    return json.dumps(payload, indent=2, default=str)[:6000]


def _format_events(events: list[dict], event_type: str) -> str:
    if not events:
        return f"No {event_type} events found in this window."
    lines = [f"Found {len(events)} {event_type} event(s):"]
    for e in events[:25]:
        start = e.get("start") or e.get("startDate")
        end = e.get("end") or e.get("endDate")
        regs = e.get("regions") or {}
        region_summary = (
            ", ".join(
                f"{k}={','.join(map(str, v))}" if isinstance(v, list) else f"{k}={v}"
                for k, v in regs.items()
                if v
            )
            or "no regions"
        )
        pos = e.get("position") or {}
        lines.append(
            f"- {start} → {end} at ({pos.get('lat')}, {pos.get('lon')}) | {region_summary}"
        )
    if len(events) > 25:
        lines.append(f"…and {len(events) - 25} more.")
    return "\n".join(lines)


@tool
def find_vessel(query: str) -> str:
    """Search Global Fishing Watch for a vessel by MMSI, IMO, name, or callsign.

    Returns the top match with the GFW vessel_id (required for the other tools),
    plus identity, ownership, and registered fishing authorizations.
    """
    try:
        records = search_vessel(query)
    except Exception as exc:
        return f"GFW vessel search failed: {exc!s}"
    if not records:
        return f"No vessels found in GFW for query {query!r}."
    best = pick_best_vessel(records, query=query) or records[0]
    summary = f"(searched GFW; {len(records)} match(es), picked the most complete record)\n"
    return summary + _format_vessel(best)


@tool
def assess_iuu_insights(vessel_id: str, days_back: int = 365) -> str:
    """Pull GFW IUU risk insights for a vessel over the last `days_back` days.

    Indicators include presence on RFMO IUU vessel lists, AIS gaps (likely
    AIS-off events), apparent fishing inside no-take MPAs, fishing outside
    authorized RFMO areas, AIS coverage stats, and flag/MMSI changes.
    """
    end_d = date.today()
    start_d = end_d - timedelta(days=days_back)
    try:
        data = get_vessel_insights(vessel_id, start_d.isoformat(), end_d.isoformat())
    except Exception as exc:
        return f"GFW insights call failed for vessel_id={vessel_id}: {exc!s}"
    return _format_insights(data)


@tool
def list_vessel_events(
    vessel_id: str,
    event_type: str = "FISHING",
    days_back: int = 90,
) -> str:
    """List GFW events for a vessel.

    event_type must be one of: FISHING, ENCOUNTER, LOITERING, PORT_VISIT, GAP.
    Each event carries time, position, and the regions (EEZ / MPA / RFMO) it
    intersects — so fishing inside an MPA or AIS gaps inside restricted zones
    are visible directly in the event payload.
    """
    end_d = date.today()
    start_d = end_d - timedelta(days=days_back)
    try:
        events = get_vessel_events(
            vessel_id, event_type.upper(), start_d.isoformat(), end_d.isoformat()
        )
    except Exception as exc:
        return f"GFW events call failed: {exc!s}"
    return _format_events(events, event_type.upper())


SYSTEM_PROMPT = """You are an IUU (Illegal, Unreported, Unregulated) fishing risk analyst backed by Global Fishing Watch data.

Pipeline (follow this order):
1. Call `find_vessel` with the user's identifier (MMSI / IMO / name) to get the GFW vessel_id and authorization profile.
2. Call `assess_iuu_insights` with that vessel_id to pull risk indicators over the requested window.
3. If insights show any concerning signal (RFMO IUU list match, gaps in MPAs, fishing outside authorizations, frequent flag/MMSI changes), call `list_vessel_events` for FISHING and then for GAP to inspect specifics.
4. Return your verdict in this exact format:

VERDICT: <HIGH RISK | MEDIUM RISK | LOW RISK | INSUFFICIENT DATA>
KEY EVIDENCE:
- <bullet — cite specific indicator or event>
- ...
CAVEATS:
- <what would need offline verification>

Calibration:
- RFMO IUU list match → HIGH (near-definitive).
- Multiple long AIS gaps that begin or end inside an MPA → HIGH.
- Recurring apparent fishing in a no-take MPA → HIGH; isolated → MEDIUM.
- Apparent fishing outside the vessel's listed RFMO authorizations → MEDIUM-HIGH.
- Frequent flag changes or MMSI changes → MEDIUM.
- No flags raised, normal authorizations, full AIS coverage → LOW.
- Vessel not found in GFW or sparse data → INSUFFICIENT DATA.

Always state that GFW indicators reflect *apparent* activity inferred from AIS + registries, not legally adjudicated illegal fishing.
"""


def build_agent_executor(model: str = "claude-sonnet-4-6") -> AgentExecutor:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    llm = ChatAnthropic(model=model, temperature=0)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ]
    )
    tools = [find_vessel, assess_iuu_insights, list_vessel_events]
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=True)


def classify_vessel(query: str, days_back: int = 365) -> str:
    executor = build_agent_executor()
    question = (
        f"Assess IUU fishing risk for vessel {query!r} using GFW data over the last "
        f"{days_back} days. Follow the pipeline and return the formatted verdict."
    )
    result = executor.invoke({"input": question})
    return result["output"] if isinstance(result, dict) else str(result)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify IUU fishing risk for a vessel using Global Fishing Watch."
    )
    parser.add_argument("query", help="MMSI, IMO, or vessel name")
    parser.add_argument(
        "days", type=int, nargs="?", default=365, help="lookback window in days"
    )
    args = parser.parse_args()
    print(classify_vessel(args.query, args.days))


if __name__ == "__main__":
    main()
