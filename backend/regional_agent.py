"""LangChain agent that returns the regional fishing laws applicable at a location.

Sources used (curated cache):
  - FAOLEX  — fisheries / food / natural-resources legislation
  - FISHLEX — Coastal State Requirements for Foreign Fishing
  - PORTLEX — port state measures (PSMA enforcement)
  - ProtectedSeas Navigator — Level of Fishing Protection (LFP) score

CLI:
    python regional_agent.py <lat> <lon>
    python regional_agent.py --region galapagos-marine-reserve
    python regional_agent.py --country PHL

Programmatic:
    from regional_agent import laws_at, laws_for_region
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
    get_region_by_country,
    get_region_by_id,
    identify_region,
    list_regions,
)

load_dotenv()


def _format_summary(region: dict) -> str:
    rule_count = len(region.get("rules") or [])
    return (
        f"REGION: {region['name']} ({region['id']})\n"
        f"Country: {region.get('country')}  |  Jurisdiction: {region.get('jurisdiction')}\n"
        f"Type: {region.get('type')}\n"
        f"Level of Fishing Protection: {region.get('level_of_fishing_protection')}\n"
        f"Rules on file: {rule_count}. "
        f"Use get_regional_rules('{region['id']}') for the full list."
    )


def _format_full(region: dict) -> str:
    return json.dumps(region, indent=2, ensure_ascii=False)


@tool
def find_region_for_coordinates(latitude: float, longitude: float) -> str:
    """Identify which cached marine jurisdiction or protected area covers the given coordinates.

    Returns a short region summary plus the region_id you can pass to
    `get_regional_rules` for the full legal text. If no cached region covers
    the point, the response lists the regions that ARE in the cache.
    """
    region = identify_region(latitude, longitude)
    if region:
        return _format_summary(region)
    known = list_regions()
    return (
        f"No cached regional rules cover ({latitude}, {longitude}). "
        f"Known regions: {json.dumps(known, indent=2)}"
    )


@tool
def get_regional_rules(region_id: str) -> str:
    """Return the full curated FAOLEX / FISHLEX / PORTLEX rule set for a region by id.

    The response is a JSON document with: rules (each with citation + source URL),
    foreign_vessel_requirements (FISHLEX), port_state_measures (PORTLEX),
    and reference URLs back to the FAO databases.
    """
    region = get_region_by_id(region_id)
    if not region:
        return f"Unknown region_id={region_id!r}. Use list_known_regions to see options."
    return _format_full(region)


@tool
def get_regional_rules_for_country(country_code: str) -> str:
    """Return curated rules for a country by ISO3 code (e.g. ECU, PHL, EU).

    Useful when a vessel's flag state or destination port is known but the
    location is not.
    """
    region = get_region_by_country(country_code)
    if not region:
        return (
            f"No cached rules for country {country_code!r}. "
            "Use list_known_regions to see what's covered."
        )
    return _format_full(region)


@tool
def list_known_regions() -> str:
    """List every region that has cached rules, with id, name, jurisdiction, and bbox."""
    return json.dumps(list_regions(), indent=2)


SYSTEM_PROMPT = """You are a fisheries legal-research assistant. Your job is to surface
the regional fishing rules that apply at a given coordinate or country, drawing on a
curated cache derived from the FAO databases (FAOLEX, FISHLEX, PORTLEX) and the
ProtectedSeas Navigator.

Pipeline:
1. If the user gives coordinates, call `find_region_for_coordinates` first. If they
   give a region id or country code, call `get_regional_rules` or
   `get_regional_rules_for_country` directly.
2. Once you have the rule set, summarize it for the user in this format:

REGION: <name> (<jurisdiction>)
PROTECTION LEVEL: <level_of_fishing_protection>
KEY RULES:
- <rule, with citation>
- ...
FOREIGN VESSEL REQUIREMENTS: <one-paragraph summary>
PORT STATE MEASURES: <one-paragraph summary>
LIKELY ILLEGAL IF: <2–4 bullets — concrete behaviors that would breach the rules above>
SOURCES:
- <FAOLEX link>
- <FISHLEX link>
- <PORTLEX link>

The "LIKELY ILLEGAL IF" block is the bridge to the IUU classifier — translate the
abstract rules into concrete observable behaviors (e.g. "AIS off inside the GMR
boundary", "fishing within 1.5 nm of an EU coastline", "trawling in Tubbataha").

If the location is not in the cache, say so clearly and suggest the closest cached
region as an analogue. Do not invent rules.
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
        find_region_for_coordinates,
        get_regional_rules,
        get_regional_rules_for_country,
        list_known_regions,
    ]
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=True)


def laws_at(latitude: float, longitude: float) -> str:
    executor = build_agent_executor()
    question = (
        f"What fishing laws apply at latitude {latitude}, longitude {longitude}? "
        "Identify the region and return the formatted summary."
    )
    result = executor.invoke({"input": question})
    return result["output"] if isinstance(result, dict) else str(result)


def laws_for_region(region_id: str) -> str:
    executor = build_agent_executor()
    question = (
        f"Return the formatted rule summary for region_id={region_id!r}."
    )
    result = executor.invoke({"input": question})
    return result["output"] if isinstance(result, dict) else str(result)


def laws_for_country(country_code: str) -> str:
    executor = build_agent_executor()
    question = (
        f"Return the formatted rule summary for country code {country_code!r}."
    )
    result = executor.invoke({"input": question})
    return result["output"] if isinstance(result, dict) else str(result)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Look up the regional fishing laws applicable at a location."
    )
    parser.add_argument("lat", type=float, nargs="?", help="latitude (decimal degrees)")
    parser.add_argument("lon", type=float, nargs="?", help="longitude (decimal degrees)")
    parser.add_argument("--region", help="resolve by cached region id instead of coords")
    parser.add_argument("--country", help="resolve by ISO3 country code instead of coords")
    args = parser.parse_args()

    if args.region:
        print(laws_for_region(args.region))
    elif args.country:
        print(laws_for_country(args.country))
    elif args.lat is not None and args.lon is not None:
        print(laws_at(args.lat, args.lon))
    else:
        parser.error("provide <lat> <lon>, or --region <id>, or --country <ISO3>")


if __name__ == "__main__":
    main()
