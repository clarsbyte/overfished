"""LangChain agent that produces a citation-backed legal dossier for a coordinate.

Architecture (per source priority):
  Input        : vessel flag, target coordinates, [optional] port country
  Geospatial   : ProtectedSeas Navigator Global Max LFP (LIVE ArcGIS)
  Legal        : FISHLEX / FAOLEX  (coastal-state rules — curated cache)
                 PORTLEX           (port-state measures — curated cache)
  Output       : verdict ∈ {ALLOWED, PERMIT_REQUIRED, PROHIBITED, HIGH_RISK,
                            INSUFFICIENT_DATA}
                 with citations: FAOLEX record(s), FISHLEX entry, PORTLEX entry,
                 ProtectedSeas LFP, last_checked dates, confidence per source.

CLI:
    python regional_agent.py <lat> <lon>
    python regional_agent.py <lat> <lon> --port-country PHL
    python regional_agent.py --region galapagos-marine-reserve
"""

from __future__ import annotations

import argparse
import json
import os

from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from country_lookup import (
    fetch_country_regulations as _fetch_country_regulations,
    resolve_country as _resolve_country,
)
from regional_lookup import (
    assemble_legal_dossier,
    geospatial_overlay,
    get_region_by_country,
    get_region_by_id,
    identify_coastal_state,
    list_cached_regions,
)
from services.legal_vectorstore import query_rules as _query_rag_rules
from services.llm import build_chat_llm

load_dotenv()

_RAG_ENABLED = os.getenv("RAG_FINETUNE", "FALSE").strip().upper() not in ("FALSE", "0", "")


def _rag_enabled() -> bool:
    """RAG_FINETUNE in .env gates the FAOLEX semantic-search tool.

    FALSE / 0 / unset → curated cache + ProtectedSeas only; the LLM never
    sees `query_faolex_rag`, so sentence-transformers / InLegalBERT weights
    are never downloaded.
    """
    return os.getenv("RAG_FINETUNE", "").strip().lower() in {"1", "true", "yes", "on"}


def _dump(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)


@tool
def lookup_protectedseas_lfp(latitude: float, longitude: float) -> str:
    """Live query the ProtectedSeas Navigator Global Max LFP FeatureServer.

    Returns the maximum Level of Fishing Protection (1–5) at the coordinate,
    its interpretation, the polygon's area and last-update date, and a
    provenance block (database, source_url, checked_at, confidence='live').
    1 = least restrictive; 5 = no-take.
    """
    try:
        return _dump(geospatial_overlay(latitude, longitude))
    except Exception as exc:
        return f"ProtectedSeas FeatureServer call failed: {exc!s}"


@tool
def lookup_coastal_state(latitude: float, longitude: float) -> str:
    """Resolve a coordinate to its coastal-state region in the curated cache.

    Returns the cache entry (FISHLEX foreign-vessel rules + FAOLEX source-law
    records + structured rules) with provenance, or a 'no match' message
    listing the cached regions if the coordinate is outside every bbox.
    """
    region = identify_coastal_state(latitude, longitude)
    if region:
        return _dump(region)
    return _dump({
        "matched": False,
        "reason": "coordinate outside all cached coastal-state bboxes",
        "cached_regions": list_cached_regions(),
    })


@tool
def lookup_portlex(country_code: str) -> str:
    """Return the PORTLEX port state measures for an ISO3 country code (e.g. ECU, PHL, EU).

    Used for port-denial / inspection / catch-certificate analysis when a vessel
    is heading to a port. Includes provenance (PORTLEX source URL + last_checked).
    """
    region = get_region_by_country(country_code)
    if not region:
        return _dump({
            "matched": False,
            "country_code": country_code,
            "reason": "country not in cache",
        })
    return _dump({
        "id": region["id"],
        "name": region["name"],
        "country": region["country"],
        "portlex": region.get("portlex"),
    })


def _format_dossier_for_llm(d: dict) -> str:
    """Compact text digest the supervisor LLM can actually fit in context.

    The full dossier JSON can run 50-60 KB (10 FAOLEX records × duplicated
    coastal+port). Past the 8K-token Ollama context, the model drops the
    original instruction and falls back to "please provide the coordinates."
    This compresses each record to a one-block digest.
    """
    lines: list[str] = []
    lines.append(f"ASSEMBLED_AT: {d.get('assembled_at')}")

    geo = d.get("geospatial") or {}
    coord = geo.get("coordinate") or {}
    ps = geo.get("protectedseas") or {}
    lines.append(
        f"COORDINATE: ({coord.get('latitude')}, {coord.get('longitude')})"
    )
    if ps.get("matched"):
        lines.append(
            f"PROTECTEDSEAS: LFP={ps.get('lfp')} ({ps.get('lfp_interpretation')}) "
            f"area={ps.get('area_sqkm')} km^2"
        )
    else:
        lines.append("PROTECTEDSEAS: no LFP polygon at this point")
    lines.append(f"  source: {(ps.get('provenance') or {}).get('source_url')}")

    cs = d.get("coastal_state")
    if cs is None:
        lines.append("\nCOASTAL_STATE: high seas — no sovereign EEZ")
    else:
        country = cs.get("country") or "?"
        name = cs.get("name") or country
        resolution = cs.get("country_resolution") or {}
        lines.append(f"\nCOASTAL_STATE: {country} ({name})")
        if resolution:
            lines.append(
                f"  resolved via {resolution.get('source')} ({resolution.get('source_url')})"
            )
        if cs.get("rules"):
            lines.append(f"  curated_rules: {len(cs['rules'])} entries")
        regs = cs.get("regulations_search") or {}
        recs = regs.get("records") or []
        if recs:
            lines.append(
                f"  faolex: {len(recs)} record(s) "
                f"(rendered={regs.get('rendered')}, cached={regs.get('cached')}, "
                f"summarized={regs.get('summarized_count')})"
            )
            lines.append(f"  search_url: {regs.get('search_url')}")
            lines.append("\nFAOLEX_RECORDS:")
            for r in recs:
                s = r.get("summary") or {}
                title = (r.get("title") or "")[:90]
                lines.append(
                    f"- {r['id']} ({r.get('year') or '?'}, {r.get('type') or '?'}): {title}"
                )
                lines.append(f"    detail: {r.get('detail_url')}")
                lines.append(
                    f"    iuu_relevant={s.get('iuu_relevant')} | "
                    f"foreign_vessels_apply={s.get('foreign_vessels_apply')}"
                )
                proh = s.get("prohibitions") or []
                if proh:
                    lines.append(f"    prohibitions: {proh[0][:160]}")
                gear = s.get("gear_restrictions") or []
                if gear:
                    lines.append(f"    gear: {gear[0][:160]}")
                area = s.get("area_restrictions") or []
                if area:
                    lines.append(f"    area: {area[0][:160]}")
                pen = s.get("penalty_summary")
                if pen:
                    lines.append(f"    penalty: {pen[:160]}")
                cite = s.get("citation_quote")
                if cite:
                    lines.append(f"    citation: {cite[:200]}")
        elif regs.get("search_url"):
            lines.append(f"  faolex: no records — search_url: {regs['search_url']}")

    port = d.get("port_state")
    if port is None:
        lines.append("\nPORT_STATE: not supplied")
    elif port.get("portlex"):
        lines.append(
            f"\nPORT_STATE: {port.get('country')} ({port.get('name')}) — curated PORTLEX present"
        )
    else:
        lines.append(
            f"\nPORT_STATE: {port.get('country')} — no curated PORTLEX; "
            f"see coastal_state FAOLEX records (same country)"
            if port.get("regulations_search_ref")
            else f"\nPORT_STATE: {port.get('country')} — no curated PORTLEX"
        )

    missing = d.get("missing") or []
    if missing:
        lines.append("\nMISSING/CAVEATS:")
        for m in missing:
            lines.append(f"- {m}")
    return "\n".join(lines)


@tool
def assemble_dossier(
    latitude: float,
    longitude: float,
    port_country_code: str | None = None,
) -> str:
    """Run the full pipeline: geospatial overlay + coastal-state legal layer + (optional) port state.

    Returns a compact TEXT digest (not JSON) tuned to fit a small-model
    context window: the geospatial result, the resolved coastal state with
    its FAOLEX records (id, year, type, title, IUU relevance, foreign-vessel
    applicability, key prohibition, gear/area/penalty signals, and a
    quotable citation per record), and the port-state block. The full JSON
    structure remains available via assemble_legal_dossier for downstream
    JSON consumers — this tool is the LLM-readable view.
    """
    try:
        d = assemble_legal_dossier(latitude, longitude, port_country_code)
    except Exception as exc:
        return f"Dossier assembly failed: {exc!s}"
    return _format_dossier_for_llm(d)


@tool
def get_region_full(region_id: str) -> str:
    """Return the full curated cache entry for a region by id (galapagos-marine-reserve, philippines-eez, eu-western-mediterranean)."""
    region = get_region_by_id(region_id)
    if not region:
        return _dump({"matched": False, "region_id": region_id})
    return _dump(region)


@tool
def list_known_regions() -> str:
    """List every cached coastal-state region (id, name, country, jurisdiction, bbox, type)."""
    return _dump(list_cached_regions())


@tool
def resolve_country_from_coord(latitude: float, longitude: float) -> str:
    """STEP 1 — Resolve a coordinate to its sovereign country (live).

    Use BEFORE fetch_country_faolex when assemble_dossier returned
    coastal_state=null (the coordinate is outside the curated bbox cache).
    Two-stage backend:
      - OSM Nominatim reverse-geocode for coastal/inland points.
      - Marine Regions WFS EEZ for offshore points outside Nominatim.
    Returns ISO3 + sovereign name + provenance, or a "high seas" note
    when neither backend places the point inside a sovereign claim.
    """
    out = _resolve_country(latitude, longitude)
    if out is None:
        return _dump({
            "matched": False,
            "reason": "high seas — neither Nominatim nor Marine Regions EEZ placed this point inside a sovereign claim. Only flag-state and RFMO rules apply.",
            "coordinate": {"latitude": latitude, "longitude": longitude},
        })
    return _dump(out)


@tool
def fetch_country_faolex(country_code: str, subject: str = "Fisheries") -> str:
    """STEP 2 — Fetch the regulatory dossier for an ISO3 country (live).

    Layered lookup, returned uniformly:
      curated   — backend/data/regional_rules.json (FISHLEX/PORTLEX/FAOLEX
                  with structured rules) — when available, this is the
                  primary citation source.
      seeded    — finetune/data/seeds/<iso3>.json — pre-discovered LEX-FAOC
                  IDs from offline FAOLEX runs.
      live      — FAOLEX country/Fisheries search URL, always returned as a
                  citation reference even when the curated/seeded layers
                  miss. FAOLEX is JS-rendered so the URL is the honest
                  citation; do not invent record IDs that aren't in the
                  returned `seeded_record_ids` or scraped `ids` lists.
    Pass the ISO3 returned by resolve_country_from_coord. `subject` defaults
    to "Fisheries"; pass "Marine resources" or "Wild fauna" for broader hits.
    """
    return _dump(_fetch_country_regulations(country_code, subject=subject))


@tool
def query_faolex_rag(query: str, country_code: str | None = None, top_k: int = 5) -> str:
    """Semantic search over FAOLEX rules extracted by a fine-tuned legal NER model.

    Use this when:
      - The curated coastal-state dossier returned no match (e.g., for CHN/IDN
        which aren't in the curated cache).
      - The curated rules don't speak to the specific gear, species, or
        penalty at hand and you need broader recall.

    Args:
      query: a free-text description of the situation. Include vessel gear,
        target species, and any zone hints. Example:
        "purse seine for bluefin tuna inside a no-take zone".
      country_code: ISO3 filter (ECU, PHL, ESP, CHN, IDN). Optional but
        strongly recommended — cross-jurisdiction noise otherwise.
      top_k: number of hits to return (default 5).

    Returns: JSON list of rule payloads. Each carries `confidence: "silver"`,
    `source_sentence`, `source_doc` (LEX-FAOC id), `source_url`, and any
    extracted species/gear/zone/prohibition/penalty_usd fields. Cite by
    quoting `source_sentence` and the source_doc — and tag the citation as
    `confidence: silver` so the verdict stays calibrated.

    Returns an `error` payload if the RAG backend isn't installed on this
    host (graceful degradation).
    """
    try:
        hits = _query_rag_rules(query=query, country=country_code, top_k=top_k)
    except Exception as exc:
        return _dump({"error": f"query_faolex_rag failed: {exc!s}"})
    return _dump(hits)


_SYSTEM_PROMPT_NO_RAG = """You are a fisheries legal-research assistant. Your job: given a
coordinate (and optionally a vessel flag, gear, species, and port-of-call), produce
a citation-backed determination of what fishing activity is legal at that point.

You draw on a source-prioritized pipeline:

  Geospatial (LIVE):
    - ProtectedSeas Navigator Global Max LFP (1–5)
  Legal (CURATED CACHE with provenance):
    - FISHLEX  : foreign-vessel rules per coastal state
    - FAOLEX   : source law records (titles, year, search/permalink URLs)
    - PORTLEX  : port state measures for IUU enforcement

Pipeline:
1. Call `assemble_dossier(latitude, longitude, port_country_code=...)`. This runs
   the geospatial + coastal-state + (optional) port-state queries in one shot.
2. If the dossier's `missing` array flags gaps you care about, follow up with the
   single-purpose tools (`lookup_protectedseas_lfp`, `lookup_coastal_state`,
   `lookup_portlex`).
3. Produce the verdict in this exact format:

VERDICT: <ALLOWED | PERMIT_REQUIRED | PROHIBITED | HIGH_RISK | INSUFFICIENT_DATA>
COORDINATE: (<lat>, <lon>)
COASTAL STATE: <name or "unknown">
LFP: <1–5 or "none"> — <interpretation>
KEY RULES:
- <rule> [FAOLEX: <citation>, source_url, last_checked, confidence]
- ...
FOREIGN VESSEL REQUIREMENTS (FISHLEX):
- <one-paragraph synthesis> [FISHLEX: source_url, last_checked, confidence]
PORT STATE MEASURES (PORTLEX, if port supplied):
- <one-paragraph synthesis> [PORTLEX: source_url, last_checked, confidence]
LIKELY ILLEGAL IF:
- <observable AIS/behavior> — translates rules into IUU classifier signals
SOURCES:
- ProtectedSeas Navigator: <source_url> (checked_at)
- FISHLEX: <source_url> (last_checked)
- PORTLEX: <source_url> (last_checked)
- FAOLEX: <one citation per key record>

Calibration:
- LFP 5 (no-take) ........................ PROHIBITED
- LFP 4 + foreign vessel ................. PROHIBITED unless explicit access agreement
- LFP 1–3 + cached rule prohibits gear/area  PROHIBITED
- LFP 1–3 + cached rule requires permit ... PERMIT_REQUIRED
- LFP 1–3 + no relevant cached rule ...... ALLOWED (low confidence — say so)
- AIS gap inside LFP ≥4 polygon .......... HIGH_RISK
- coastal_state is null ................... INSUFFICIENT_DATA — do NOT invent rules

Hard rules:
- Every claim must cite at least one of FAOLEX / FISHLEX / PORTLEX / ProtectedSeas
  with the source_url and last_checked date from the dossier.
- Never write "AI inferred". If a layer's confidence is "curated", say "curated";
  if "live", say "live"; if no source covers a question, say INSUFFICIENT_DATA
  for that point and recommend the operator consult the linked FAO database.
"""

_SYSTEM_PROMPT_RAG = """You are a fisheries legal-research assistant. Your job: given a
coordinate (and optionally a vessel flag, gear, species, and port-of-call), produce
a citation-backed determination of what fishing activity is legal at that point.

You draw on a source-prioritized pipeline:

  Geospatial (LIVE):
    - ProtectedSeas Navigator Global Max LFP (1–5)
  Legal (CURATED CACHE with provenance):
    - FISHLEX  : foreign-vessel rules per coastal state
    - FAOLEX   : source law records (titles, year, search/permalink URLs)
    - PORTLEX  : port state measures for IUU enforcement
  Legal (SEMANTIC RETRIEVAL, confidence='silver'):
    - query_faolex_rag : embedding search over rules extracted from full
      FAOLEX text by a fine-tuned legal NER model. Coverage: ECU, PHL,
      ESP, CHN, IDN. Lower precision than the curated cache; treat as
      supplementary evidence, not primary law.

Pipeline (follow this order — STEP BY STEP):
1. Call `assemble_dossier(latitude, longitude, port_country_code=...)`. This already
   chains the geospatial overlay → coastal-state cache lookup → live country resolve
   → FAOLEX search-URL probe → port-state lookup. Read its `missing` array first.

2. If `assemble_dossier` returned `coastal_state` with `country_resolution.source`
   set to "nominatim" or starting with "marine_regions:", the country WAS
   resolved live — the ISO3 is in `coastal_state.country` and a FAOLEX search
   URL is in `coastal_state.regulations_search.search_url`. Cite that URL as
   your primary FAOLEX reference; do NOT invent record IDs.

3. If `coastal_state` is null (high seas), the point is outside every sovereign
   EEZ. Only flag-state and RFMO rules apply. Set verdict=INSUFFICIENT_DATA
   and recommend operator consult the relevant RFMO.

4. STEPWISE FALLBACK if step 1 didn't run / partially failed:
   a. Call `resolve_country_from_coord(lat, lon)` to get ISO3 + sovereign.
   b. Call `fetch_country_faolex(country_code=<iso3>)` to get the dossier
      for that country. Cite the `provenance.search_url` it returns.

5. If the curated dossier doesn't speak to a specific gear/species/penalty,
   AND `query_faolex_rag` is registered (RAG_FINETUNE=TRUE), call it with
   the vessel context. Otherwise rely on the curated rules and the FAOLEX
   search URL.

6. Produce the verdict in this exact format:

VERDICT: <ALLOWED | PERMIT_REQUIRED | PROHIBITED | HIGH_RISK | INSUFFICIENT_DATA>
COORDINATE: (<lat>, <lon>)
COASTAL STATE: <name or "unknown">
LFP: <1–5 or "none"> — <interpretation>
KEY RULES:
- <rule> [FAOLEX: <citation>, source_url, last_checked, confidence]
- ...
FOREIGN VESSEL REQUIREMENTS (FISHLEX):
- <one-paragraph synthesis> [FISHLEX: source_url, last_checked, confidence]
PORT STATE MEASURES (PORTLEX, if port supplied):
- <one-paragraph synthesis> [PORTLEX: source_url, last_checked, confidence]
LIKELY ILLEGAL IF:
- <observable AIS/behavior> — translates rules into IUU classifier signals
SOURCES:
- ProtectedSeas Navigator: <source_url> (checked_at)
- FISHLEX: <source_url> (last_checked)
- PORTLEX: <source_url> (last_checked)
- FAOLEX: <one citation per key record>

Calibration:
- LFP 5 (no-take) ........................ PROHIBITED
- LFP 4 + foreign vessel ................. PROHIBITED unless explicit access agreement
- LFP 1–3 + cached rule prohibits gear/area  PROHIBITED
- LFP 1–3 + cached rule requires permit ... PERMIT_REQUIRED
- LFP 1–3 + no relevant cached rule ...... ALLOWED (low confidence — say so)
- AIS gap inside LFP ≥4 polygon .......... HIGH_RISK
- coastal_state is null ................... INSUFFICIENT_DATA — do NOT invent rules

Hard rules:
- Every claim must cite at least one of FAOLEX / FISHLEX / PORTLEX / ProtectedSeas
  with the source_url and last_checked date from the dossier.
- Never write "AI inferred". If a layer's confidence is "curated", say "curated";
  if "live", say "live"; if "silver" (from query_faolex_rag), say "silver" and
  do not promote it to "curated"; if no source covers a question, say
  INSUFFICIENT_DATA for that point and recommend the operator consult the
  linked FAO database.
"""

SYSTEM_PROMPT = _SYSTEM_PROMPT_RAG if _RAG_ENABLED else _SYSTEM_PROMPT_NO_RAG


def build_agent_executor(model: str | None = None) -> AgentExecutor:
    llm = build_chat_llm("heavy", model=model)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ]
    )
    tools = [
        assemble_dossier,
        lookup_protectedseas_lfp,
        lookup_coastal_state,
        lookup_portlex,
        resolve_country_from_coord,
        fetch_country_faolex,
        get_region_full,
        list_known_regions,
    ]
    if _rag_enabled():
        tools.append(query_faolex_rag)
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=True)


def _format_model_context_block(ctx: dict | None) -> str:
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


def evaluate_point(
    latitude: float,
    longitude: float,
    port_country_code: str | None = None,
    vessel_flag: str | None = None,
    gear: str | None = None,
    species: str | None = None,
    model_context: dict | None = None,
) -> str:
    executor = build_agent_executor()
    extras = []
    if vessel_flag:
        extras.append(f"vessel flag = {vessel_flag}")
    if gear:
        extras.append(f"gear = {gear}")
    if species:
        extras.append(f"target species = {species}")
    if port_country_code:
        extras.append(f"port country = {port_country_code}")
    extras_str = (" Context: " + "; ".join(extras) + ".") if extras else ""
    model_block = _format_model_context_block(model_context)
    prefix = (model_block + "\n\n") if model_block else ""
    question = (
        f"{prefix}"
        f"Evaluate fishing legality at latitude {latitude}, longitude {longitude}."
        f"{extras_str} Run the dossier pipeline and return the formatted verdict."
    )
    result = executor.invoke({"input": question})
    return result["output"] if isinstance(result, dict) else str(result)


def evaluate_region(region_id: str) -> str:
    executor = build_agent_executor()
    question = (
        f"Return the formatted rule summary for region_id={region_id!r}, including the "
        "FISHLEX / PORTLEX / FAOLEX citations."
    )
    result = executor.invoke({"input": question})
    return result["output"] if isinstance(result, dict) else str(result)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Look up fishing legality at a coordinate using the prioritized FAO + ProtectedSeas pipeline."
    )
    parser.add_argument("lat", type=float, nargs="?", help="latitude (decimal degrees)")
    parser.add_argument("lon", type=float, nargs="?", help="longitude (decimal degrees)")
    parser.add_argument("--region", help="resolve by cached region id instead of coords")
    parser.add_argument("--port-country", dest="port_country", help="ISO3 port country code")
    parser.add_argument("--flag", help="vessel flag state (ISO3)")
    parser.add_argument("--gear", help="gear type (e.g. trawl, longline, purse-seine)")
    parser.add_argument("--species", help="target species")
    args = parser.parse_args()

    if args.region:
        print(evaluate_region(args.region))
    elif args.lat is not None and args.lon is not None:
        print(
            evaluate_point(
                args.lat,
                args.lon,
                port_country_code=args.port_country,
                vessel_flag=args.flag,
                gear=args.gear,
                species=args.species,
            )
        )
    else:
        parser.error("provide <lat> <lon>, or --region <id>")


if __name__ == "__main__":
    main()
