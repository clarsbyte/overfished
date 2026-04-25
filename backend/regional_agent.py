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
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from regional_lookup import (
    assemble_legal_dossier,
    geospatial_overlay,
    get_region_by_country,
    get_region_by_id,
    identify_coastal_state,
    list_cached_regions,
)
from services.legal_vectorstore import query_rules as _query_rag_rules

load_dotenv()


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


@tool
def assemble_dossier(
    latitude: float,
    longitude: float,
    port_country_code: str | None = None,
) -> str:
    """Run the full pipeline: geospatial overlay + coastal-state legal layer + (optional) port state.

    Returns a single JSON document with: ProtectedSeas LFP, coastal-state
    FISHLEX / FAOLEX, optional PORTLEX, an `assembled_at` timestamp, and a
    `missing` array listing any layers that returned no match. This is the
    fastest path to a complete answer; the other tools are for follow-ups.
    """
    try:
        return _dump(assemble_legal_dossier(latitude, longitude, port_country_code))
    except Exception as exc:
        return f"Dossier assembly failed: {exc!s}"


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


SYSTEM_PROMPT = """You are a fisheries legal-research assistant. Your job: given a
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

Pipeline:
1. Call `assemble_dossier(latitude, longitude, port_country_code=...)`. This runs
   the geospatial + coastal-state + (optional) port-state queries in one shot.
2. If the dossier's `missing` array flags gaps you care about, follow up with the
   single-purpose tools (`lookup_protectedseas_lfp`, `lookup_coastal_state`,
   `lookup_portlex`).
2b. If the curated dossier doesn't speak to the specific gear/species/penalty,
   OR the coastal-state lookup missed but the country is in the indexed set
   (ECU/PHL/ESP/CHN/IDN), call `query_faolex_rag(query=<vessel context>,
   country_code=<iso3>)`. Quote returned `source_sentence`s and tag those
   citations explicitly as `confidence: silver`. When a curated rule and a
   silver rule speak to the same point, prefer the curated rule.
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
  if "live", say "live"; if "silver" (from query_faolex_rag), say "silver" and
  do not promote it to "curated"; if no source covers a question, say
  INSUFFICIENT_DATA for that point and recommend the operator consult the
  linked FAO database.
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
    tools = [
        assemble_dossier,
        lookup_protectedseas_lfp,
        lookup_coastal_state,
        lookup_portlex,
        get_region_full,
        list_known_regions,
        query_faolex_rag,
    ]
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=True)


def evaluate_point(
    latitude: float,
    longitude: float,
    port_country_code: str | None = None,
    vessel_flag: str | None = None,
    gear: str | None = None,
    species: str | None = None,
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
    question = (
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
