"""Regulation extraction & legal-citation roster assembly.

Real mode would FAOLEX-scrape + Gemini-extract. Fixture mode loads pre-baked
rules and citations for the Galápagos demo.
"""

from __future__ import annotations

import os

from fixtures._loader import load_models
from tools.schemas import IUURule, LegalCitation, RegionContext, Vessel, VesselEvent

_USE_FIXTURES = os.getenv("USE_FIXTURES", "1") == "1"


def fetch_regional_regulations(region: RegionContext) -> list[dict]:
    """Pull candidate legal documents across the four layers."""
    if _USE_FIXTURES:
        return [
            {
                "title": "Organic Law of the Special Regime for the Province of Galápagos",
                "url": "https://faolex.fao.org/docs/texts/ecu/loreg.txt",
                "source": "FAOLEX",
                "layer": "national",
                "date": "2015-06-12",
            },
            {
                "title": "FAO Port State Measures Agreement",
                "url": "https://www.fao.org/port-state-measures",
                "source": "FAO",
                "layer": "international",
                "date": "2009-11-22",
            },
            {
                "title": "IATTC Resolution C-19-01",
                "url": "https://www.iattc.org/PDFFiles/Resolutions/IATTC/_English/C-19-01-Active_Vessel-Registry.pdf",
                "source": "IATTC",
                "layer": "rfmo",
                "date": "2019-07-26",
            },
        ]
    raise NotImplementedError("set USE_FIXTURES=1")


def extract_iuu_rules(documents: list[dict], region: RegionContext) -> list[IUURule]:
    """LLM extraction stand-in. Fixture mode just loads the pre-extracted set."""
    if _USE_FIXTURES:
        return load_models("rules_galapagos", IUURule)
    raise NotImplementedError("set USE_FIXTURES=1")


def build_citation_roster(
    rules_triggered: list[IUURule],
    region: RegionContext,
) -> list[LegalCitation]:
    """Assemble the layered citation roster for documents.

    Anti-redundancy: at most one citation per (layer, role) pair.
    """
    if _USE_FIXTURES:
        all_citations = load_models("citations_galapagos", LegalCitation)
        seen: set[tuple[str, str]] = set()
        deduped: list[LegalCitation] = []
        for c in all_citations:
            key = (c.layer, c.role)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(c)
        return deduped
    raise NotImplementedError("set USE_FIXTURES=1")


def evaluate_rule_against_vessel(
    rule: IUURule,
    vessel: Vessel,
    events: list[VesselEvent],
    region: RegionContext,
) -> tuple[bool, str]:
    """Returns (triggered, reasoning)."""
    if _USE_FIXTURES:
        # Hardcoded mapping for the demo. Real mode runs the structured machine_check.
        if rule.rule_id == "rule-loreg-75a":
            has_gap = any(e.type == "GAP" for e in events)
            return has_gap, (
                "Vessel transited inside no-take Zone 2.1 during a 7h45m AIS gap; "
                "fishing event observed during the gap window."
            ) if has_gap else "No GAP event observed."
        if rule.rule_id == "rule-iattc-c-19-01":
            unregistered = not any(a.startswith("IATTC-") for a in vessel.authorizations)
            return unregistered, (
                "Vessel does not appear on the IATTC Regional Vessel Register."
            ) if unregistered else "Vessel is IATTC-registered."
        if rule.rule_id == "rule-solas-v-19":
            gaps = [e for e in events if e.type == "GAP" and (e.duration_hours or 0) > 0]
            return bool(gaps), (
                f"AIS transmission disabled for {gaps[0].duration_hours:.2f} hours."
            ) if gaps else "No AIS gap observed."
        if rule.rule_id == "rule-unclos-73":
            return True, "Vessel inside Ecuador's EEZ; flag state ≠ ECU."
        return False, "Rule not exercised in fixture demo."
    raise NotImplementedError("set USE_FIXTURES=1")
