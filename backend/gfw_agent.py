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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

from dotenv import load_dotenv
from langchain_core.tools import tool

from comms_lookup import generate_vessel_warning
from gfw_lookup import (
    VesselRecord,
    get_vessel_events,
    get_vessel_insights,
    is_fishing_vessel,
    pick_best_vessel,
    search_vessel,
)
from services.llm import build_chat_llm

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
    ship_types = ", ".join(v.ship_types) or "(none on record)"
    gear_types = ", ".join(v.gear_types) or "(none on record)"
    return (
        f"vessel_id: {v.vessel_id}\n"
        f"name: {v.name or 'Unknown'}\n"
        f"mmsi: {v.mmsi}  imo: {v.imo}  callsign: {v.callsign}\n"
        f"flag: {v.flag}\n"
        f"ship_types (all entries): {ship_types}\n"
        f"gear_types (all entries): {gear_types}\n"
        f"primary ship_type: {v.ship_type}  primary gear_type: {v.gear_type}\n"
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


@tool
def send_vessel_warning(
    vessel_name: str,
    mmsi: str,
    violations_summary: str,
    phone_number: str | None = None,
) -> str:
    """Generate a spoken audio warning for a vessel via ElevenLabs TTS.

    Only call this when the user explicitly requests an audio warning or phone call.
    Pass the vessel's display name, MMSI, and a concise summary of the violations.
    If phone_number is provided (E.164 format e.g. "+15551234567"), also places a
    Twilio call to that number playing the audio — requires AUDIO_BASE_URL in .env.
    """
    try:
        if phone_number:
            audio_base_url = os.getenv("AUDIO_BASE_URL", "").strip()
            if not audio_base_url:
                return (
                    "Phone call requested but AUDIO_BASE_URL is not set in .env. "
                    "Set it to your server's /audio URL (e.g. http://localhost:8000/audio)."
                )
            from comms_lookup import generate_and_call
            result = generate_and_call(vessel_name, mmsi, violations_summary, phone_number, audio_base_url)
            return (
                f"Audio warning generated and call placed.\n"
                f"Message: {result['message']}\n"
                f"Audio URL: {result['audio_url']}\n"
                f"Call SID: {result['call_sid']}"
            )
        result = generate_vessel_warning(vessel_name, mmsi, violations_summary)
        return (
            f"Audio warning generated.\n"
            f"Message: {result['message']}\n"
            f"File: {result['audio_path']}"
        )
    except Exception as exc:
        return f"Warning generation failed: {exc!s}"


SYSTEM_PROMPT = """You are an IUU (Illegal, Unreported, Unregulated) fishing risk analyst backed by Global Fishing Watch data.

Pipeline (follow this order):
1. Call `find_vessel` with the user's identifier (MMSI / IMO / name) to get the GFW vessel_id and authorization profile.
2. FISHING-VESSEL GATE — before any IUU assessment:
   - Inspect the FULL `ship_types (all entries)` and `gear_types (all entries)`
     lists from find_vessel — these aggregate every classification GFW has
     recorded across the vessel's identity periods (this is what the GFW
     website surfaces as the vessel's "type").
   - The vessel IS a fishing vessel if EITHER:
     a) gear_types is non-empty (any gear like PURSE_SEINES, TRAWLERS,
        POTS_AND_TRAPS, SET_GILLNETS, ... means fishing-capable by construction), OR
     b) ship_types contains "FISHING".
   - Only if BOTH lists fail those checks (e.g. ship_types=[CARGO] / [TANKER] /
     [PASSENGER] / [TUG] / [PLEASURE_CRAFT] with empty gear_types), STOP the
     pipeline and return:
       VERDICT: NOT A FISHING VESSEL
       KEY EVIDENCE:
       - ship_types=<list>, gear_types=<list or none> — vessel is not fishing-capable
       CAVEATS:
       - IUU fishing indicators do not apply to non-fishing vessels.
     Do NOT call assess_iuu_insights or list_vessel_events.
3. Call `assess_iuu_insights` with that vessel_id to pull risk indicators over the requested window.
4. If insights show any concerning signal (RFMO IUU list match, gaps in MPAs, fishing outside authorizations, frequent flag/MMSI changes), call `list_vessel_events` for FISHING and then for GAP to inspect specifics.
5. Return your verdict in this exact format:

VERDICT: <HIGH RISK | MEDIUM RISK | LOW RISK | INSUFFICIENT DATA | NOT A FISHING VESSEL>
KEY EVIDENCE:
- <bullet — cite specific indicator or event>
- ...
CAVEATS:
- <what would need offline verification>

ANTI-BIAS RULE — read this before assigning a verdict:
- The base rate of IUU fishing among any random vessel is small. DEFAULT to LOW
  unless GFW data shows a SPECIFIC, NAMED indicator. "Could be", "potentially",
  "the data is unclear" → that is LOW or INSUFFICIENT DATA, not MEDIUM.
- Do not infer IUU risk from a vessel simply being present in a region. The
  pipeline already filtered by region; presence alone is not evidence.
- Do not escalate on absence of authorizations alone — most of the world's
  fishing fleet has no RFMO authorization on file. Absence of authorization
  is only an escalator if combined with apparent fishing inside an RFMO area
  that requires authorization.

Calibration (apply only after the anti-bias rule):
- RFMO IUU list match (vesselIdentity.iuuVesselList non-empty) → HIGH (near-definitive).
- Two or more long AIS gaps (>12 h) that begin or end inside an MPA → HIGH.
- Recurring apparent fishing inside a no-take MPA (>=3 events, >=2 distinct days) → HIGH.
- A single isolated apparent-fishing event inside a no-take MPA → MEDIUM.
- Apparent fishing inside an RFMO area where the vessel has no listed authorization
  for that RFMO (eventsInRfmoWithoutKnownAuthorization non-empty) → MEDIUM.
- Documented flag-of-convenience pattern: 3+ flag changes in 5 years → MEDIUM.
- Single AIS gap, normal authorizations, no MPA activity → LOW.
- Vessel not found in GFW, or insights endpoint returns empty period counters → INSUFFICIENT DATA.

If your verdict is HIGH or MEDIUM, your KEY EVIDENCE bullets MUST cite the
specific indicator from the insights or events response (e.g. "gap event
2024-03-15→2024-03-19 ending inside MPA Tubbataha", "iuuVesselList=['CCAMLR']").
A verdict without a cited indicator must be downgraded to LOW.

Always state that GFW indicators reflect *apparent* activity inferred from AIS + registries, not legally adjudicated illegal fishing.

Audio warnings:
- Only call `send_vessel_warning` when the user explicitly asks for an audio warning or message to be sent to the vessel.
- Never call it automatically as part of a risk assessment.
- When called, pass the vessel name, MMSI, and a concise 1–2 sentence summary of the key violations.
"""


def build_agent_executor(model: str | None = None):
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_core.prompts import ChatPromptTemplate
    llm = build_chat_llm("light", model=model)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ]
    )
    tools = [find_vessel, assess_iuu_insights, list_vessel_events, send_vessel_warning]
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=True)


def _format_model_context_block(ctx: dict | None) -> str:
    """Render ModelContext (LangChain static-runtime-context payload) for the prompt."""
    if not ctx:
        return ""
    selected = ctx.get("selected") or None
    if not selected and not ctx.get("nearby") and not ctx.get("report_narration"):
        return ""
    lines = [
        "MODEL CONTEXT (RNN+BiLSTM, soft-prob ensemble; treat as triage, not ground truth):"
    ]
    if selected:
        risk_tag = str(selected.get("model_risk", "?")).upper()
        p = float(selected.get("mean_confidence") or 0.0)
        alias = selected.get("alias_mmsi")
        alias_share = float(selected.get("alias_share") or 0.0)
        alias_bit = (
            f", alias candidate {alias} in {alias_share:.0%} of windows" if alias else ""
        )
        lines.append(
            f"- Selected MMSI {selected.get('mmsi', '?')} -> {risk_tag} "
            f"(mean P {p:.0%}{alias_bit})."
        )
        if selected.get("narration"):
            lines.append(f"  {selected.get('narration')}")
    if ctx.get("report_narration"):
        lines.append(f"- Report summary: {ctx.get('report_narration')}")
    return "\n".join(lines)


_CLASSIFY_PROMPT = """\
You are an IUU fishing risk analyst. All GFW data has been pre-fetched — do NOT call any tools.
Analyse the data below and return your verdict in the exact format shown.

--- VESSEL IDENTITY ---
{vessel}

--- IUU INSIGHTS (last {days_back} days) ---
{insights}

--- FISHING EVENTS (last {days_back} days) ---
{fishing_events}

--- AIS GAP EVENTS (last {days_back} days) ---
{gap_events}

Calibration rules (apply after anti-bias check — default to LOW unless a named indicator is present):
- RFMO IUU list match → HIGH
- Two+ long AIS gaps (>12 h) starting/ending inside an MPA → HIGH
- Recurring apparent fishing inside a no-take MPA (>=3 events, >=2 days) → HIGH
- Single apparent-fishing event inside a no-take MPA → MEDIUM
- Fishing inside an RFMO area without known authorisation → MEDIUM
- 3+ flag changes in 5 years → MEDIUM
- Single AIS gap, normal authorisations, no MPA activity → LOW
- Vessel not in GFW or empty insights → INSUFFICIENT DATA

Return ONLY this format — no extra commentary:

VERDICT: <HIGH RISK | MEDIUM RISK | LOW RISK | INSUFFICIENT DATA>
KEY EVIDENCE:
- <cite the specific indicator, event id, MPA name, date range>
CAVEATS:
- GFW indicators reflect *apparent* activity inferred from AIS + registries, not legally adjudicated illegal fishing.
"""


def _prefetch_vessel_data(query: str, days_back: int) -> dict:
    """Fetch vessel identity + insights + events in parallel. Returns structured dict."""
    end_d = date.today()
    start_iso = (end_d - timedelta(days=days_back)).isoformat()
    end_iso = end_d.isoformat()

    try:
        records = search_vessel(query)
    except Exception as exc:
        return {"error": f"GFW vessel search failed: {exc}"}
    if not records:
        return {"error": f"No vessels found in GFW for {query!r}"}

    vessel = pick_best_vessel(records, query=query) or records[0]

    fetches: dict = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = {
            pool.submit(get_vessel_insights, vessel.vessel_id, start_iso, end_iso): "insights",
            pool.submit(get_vessel_events, vessel.vessel_id, "FISHING", start_iso, end_iso): "fishing",
            pool.submit(get_vessel_events, vessel.vessel_id, "GAP", start_iso, end_iso): "gap",
        }
        for fut in as_completed(futs):
            key = futs[fut]
            try:
                fetches[key] = fut.result()
            except Exception:
                fetches[key] = {} if key == "insights" else []

    return {
        "vessel": vessel,
        "insights": fetches.get("insights", {}),
        "fishing_events": fetches.get("fishing", []),
        "gap_events": fetches.get("gap", []),
        "error": None,
    }


def classify_vessel(query: str, days_back: int = 365) -> str:
    """Classify IUU risk for one vessel via prefetch + direct gemma3 call (no tool loop)."""
    data = _prefetch_vessel_data(query, days_back)

    if data.get("error"):
        return (
            f"VERDICT: INSUFFICIENT DATA\n"
            f"KEY EVIDENCE:\n- {data['error']}\n"
            "CAVEATS:\n- GFW lookup failed; cannot assess risk."
        )

    vessel: VesselRecord = data["vessel"]

    # Apply fishing-vessel gate in Python — no LLM needed for this check.
    if not is_fishing_vessel(vessel):
        return (
            "VERDICT: NOT A FISHING VESSEL\n"
            "KEY EVIDENCE:\n"
            f"- ship_types={vessel.ship_types}, gear_types={vessel.gear_types or '(none)'}"
            " — vessel is not fishing-capable\n"
            "CAVEATS:\n- IUU fishing indicators do not apply to non-fishing vessels."
        )

    prompt = _CLASSIFY_PROMPT.format(
        vessel=_format_vessel(vessel),
        insights=_format_insights(data["insights"]),
        fishing_events=_format_events(data["fishing_events"], "FISHING"),
        gap_events=_format_events(data["gap_events"], "GAP"),
        days_back=days_back,
    )

    llm = build_chat_llm("light", model="gemma3:4b")
    response = llm.invoke(prompt)
    body = response.content if hasattr(response, "content") else str(response)
    if isinstance(body, list):
        body = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in body)
    return body.strip()


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
