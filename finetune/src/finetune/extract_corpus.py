"""Extract structured rule tuples from fetched FAOLEX documents.

Two modes:
  --mode stub  (default until weights exist)
       Regex + keyword spotter for SPECIES, GEAR, ZONE, PROHIBITION,
       PENALTY (USD), LICENSE. Lower recall but correctly-shaped tuples,
       enough to demo the full RAG pipeline before fine-tuning completes.

  --mode ner   (after `python -m finetune.train` produces weights)
       Loads backend.services.legal_extractor.extract_rules_ner, which
       runs the fine-tuned LegalBERT token classifier.

Reads:
    finetune/data/raw/<iso3>/*.json  (output of fetch_faolex.py)

Writes:
    finetune/data/extracted_rules.jsonl
        {country, source_doc, source_url, source_sentence, species, gear,
         zone, prohibition, penalty_usd, license, confidence, extracted_at}
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
OUT_PATH = ROOT / "data" / "extracted_rules.jsonl"

SPECIES = {
    # Tunas & billfish
    "tuna", "yellowfin", "bigeye", "skipjack", "bluefin", "albacore",
    "swordfish", "marlin", "sailfish", "spearfish",
    # Sharks & rays
    "shark", "hammerhead", "ray", "manta", "skate", "sawfish",
    # Small pelagics
    "sardine", "anchovy", "mackerel", "herring", "sprat", "pilchard", "whitebait",
    # Groundfish
    "cod", "haddock", "pollock", "hake", "halibut", "flatfish", "sole", "turbot",
    "rockfish", "sea bass", "sea bream", "snapper", "grouper",
    # Cephalopods
    "octopus", "squid", "cuttlefish",
    # Crustaceans
    "lobster", "crab", "shrimp", "prawn", "krill",
    # Shellfish
    "scallop", "abalone", "mussel", "oyster", "clam", "cockle",
    # Other
    "sea cucumber", "eel", "salmon", "trout", "trevally", "wahoo",
    "mahi", "amberjack", "barramundi", "milkfish", "tilapia", "catfish",
    # Protected megafauna commonly cited in fishing regs
    "sea turtle", "turtle", "whale", "dolphin", "dugong", "porpoise",
    # Generic
    "fish", "seafood", "marine species", "aquatic species",
}
GEAR = {
    # Trawls
    "trawl", "trawler", "trawling", "bottom trawl", "midwater trawl", "beam trawl",
    # Lines
    "longline", "long-line", "long line", "hook and line", "pole and line",
    # Nets
    "gillnet", "gill net", "drift net", "driftnet", "cast net", "throw net",
    "purse seine", "seine net", "seiner", "surround net",
    "fyke net", "pound net", "set net", "trammel net",
    # Traps & pots
    "trap", "pot", "fish trap", "crab pot",
    # Other gear
    "dredge", "dredging", "harpoon", "spear", "speargun",
    "fad", "fish aggregating device",
    # Prohibited methods
    "explosives", "dynamite", "poison", "cyanide", "electric",
    # Generic
    "fishing gear", "fishing equipment", "fishing net", "net",
    "aquaculture", "fish farm",
}
ZONE = {
    # Jurisdictional zones
    "eez", "exclusive economic zone",
    "territorial sea", "territorial waters",
    "contiguous zone", "continental shelf",
    "high seas", "international waters",
    # Protected areas
    "marine reserve", "marine protected area", "mpa",
    "marine sanctuary", "marine park",
    "no-take", "no take zone", "no-take zone",
    "fish refuge", "fish sanctuary",
    # Coastal / management zones
    "coastal zone", "coastal waters", "inshore", "offshore",
    "spawning ground", "nursery area", "critical habitat",
    # Closures
    "closed area", "closure area", "restricted area",
    "fishing zone", "management zone",
}
# General fisheries activity terms — used as a third subject category so that
# sentences about "fishing vessels" or "catch limits" without specific species
# names still qualify.
FISHING_GENERAL = {
    "fishing", "fishery", "fisheries", "fisher", "fisherman", "fishermen",
    "vessel", "fishing vessel", "fishing boat", "fishing craft", "fishing fleet",
    "catch", "bycatch", "by-catch", "incidental catch", "discards",
    "quota", "catch limit", "total allowable catch", "tac",
    "harvest", "harvesting",
    "landing", "landings", "landed catch",
    "bag limit", "size limit", "minimum size", "minimum length",
    "closed season", "open season", "spawning season", "fishing season",
    "marine resource", "aquatic resource", "fish stock", "fishery resource",
    "iuu", "illegal fishing", "unreported fishing", "unregulated fishing",
}
# Season / temporal closure terms — a sentence mentioning one of these + any
# rule signal qualifies even without a species or gear name.
SEASON_CLOSURE = {
    "closed season", "close season", "open season",
    "spawning season", "spawning period", "breeding season",
    "fishing ban", "fishing moratorium", "temporary ban",
    "closed area", "closure", "fishing closure",
    "seasonal restriction", "seasonal prohibition",
}
LICENSE_HINTS = {
    "license required", "licence required",
    "permit required",
    "authorization required", "authorisation required",
    "subject to license", "subject to permit",
    "shall hold a license", "shall hold a permit",
    "with prior authorization", "with prior authorisation",
    # Expanded
    "shall obtain a license", "shall obtain a permit",
    "must hold a license", "must hold a permit",
    "fishing license", "fishing licence", "fishing permit",
    "vessel registration", "vessel license", "vessel licence",
    "import permit", "export permit",
}
PROHIBITION_PHRASES = [
    # Original
    re.compile(r"\bshall not\b", re.IGNORECASE),
    re.compile(r"\bis prohibited\b", re.IGNORECASE),
    re.compile(r"\bare prohibited\b", re.IGNORECASE),
    re.compile(r"\bforbidden\b", re.IGNORECASE),
    re.compile(r"\bbanned\b", re.IGNORECASE),
    re.compile(r"\bnot permitted\b", re.IGNORECASE),
    re.compile(r"\bunlawful\b", re.IGNORECASE),
    re.compile(r"\bno person shall\b", re.IGNORECASE),
    # Expanded prohibitions
    re.compile(r"\bmay not\b", re.IGNORECASE),
    re.compile(r"\bmust not\b", re.IGNORECASE),
    re.compile(r"\bno fishing\b", re.IGNORECASE),
    re.compile(r"\bprohibit\w*\b", re.IGNORECASE),
    re.compile(r"\brestrict\w*\b", re.IGNORECASE),
    re.compile(r"\bclosed to\b", re.IGNORECASE),
    re.compile(r"\bno person\b", re.IGNORECASE),
    re.compile(r"\bit is an offence\b", re.IGNORECASE),
    re.compile(r"\bconstitutes an offence\b", re.IGNORECASE),
    re.compile(r"\boffence\b", re.IGNORECASE),
    re.compile(r"\bviolation\b", re.IGNORECASE),
    re.compile(r"\binfringement\b", re.IGNORECASE),
    # Penalties / enforcement
    re.compile(r"\bshall be liable\b", re.IGNORECASE),
    re.compile(r"\bimprisonment\b", re.IGNORECASE),
    re.compile(r"\bimprisoned\b", re.IGNORECASE),
    re.compile(r"\bfine of\b", re.IGNORECASE),
    re.compile(r"\bpenalt\w*\b", re.IGNORECASE),
    re.compile(r"\bforfeiture\b", re.IGNORECASE),
    re.compile(r"\bconfiscat\w*\b", re.IGNORECASE),
    re.compile(r"\bseizure\b", re.IGNORECASE),
    # Obligations / conditions
    re.compile(r"\bshall obtain\b", re.IGNORECASE),
    re.compile(r"\bshall ensure\b", re.IGNORECASE),
    re.compile(r"\bshall report\b", re.IGNORECASE),
    re.compile(r"\bshall carry\b", re.IGNORECASE),
    re.compile(r"\bshall comply\b", re.IGNORECASE),
    re.compile(r"\bmust comply\b", re.IGNORECASE),
    re.compile(r"\bsubject to\b", re.IGNORECASE),
    re.compile(r"\brequired to\b", re.IGNORECASE),
    re.compile(r"\bobligat\w*\b", re.IGNORECASE),
    # Season / quota signals
    re.compile(r"\bduring the closed season\b", re.IGNORECASE),
    re.compile(r"\bduring the period\b", re.IGNORECASE),
    re.compile(r"\bexceed\w*\b.*\bquota\b", re.IGNORECASE),
    re.compile(r"\bquota\b.*\bexceed\w*\b", re.IGNORECASE),
    re.compile(r"\bcatch limit\b", re.IGNORECASE),
    re.compile(r"\btotal allowable catch\b", re.IGNORECASE),
    re.compile(r"\bminimum size\b", re.IGNORECASE),
    re.compile(r"\bminimum length\b", re.IGNORECASE),
    re.compile(r"\bsize limit\b", re.IGNORECASE),
]
# $50,000 / USD 1,200,000 / 10,000 dollars / EUR 5,000
PENALTY_RE = re.compile(
    r"(?:US\$?|USD|EUR|GBP|\$|€|£)\s*([\d,]+(?:\.\d+)?)"
    r"|"
    r"([\d,]+(?:\.\d+)?)\s*(?:US\s*)?dollars?\b",
    re.IGNORECASE,
)


def _split_sentences(text: str) -> list[str]:
    """Lightweight sentence splitter — no nltk dependency at runtime.

    Splits on `.`, `?`, `!` followed by whitespace, but not on common
    abbreviations (Art., No., Sec.). Good enough for FAOLEX prose.
    """
    text = re.sub(r"\s+", " ", text)
    abbrev = re.compile(r"(Art|Arts|No|Sec|Cap|cf|e\.g|i\.e|Mr|Ms|St)\.\s")
    placeholder = "\x00"
    text = abbrev.sub(lambda m: m.group(0).replace(".", placeholder), text)
    parts = re.split(r"(?<=[.?!])\s+(?=[A-ZÀ-ſ0-9])", text)
    return [p.replace(placeholder, ".").strip() for p in parts if len(p.strip()) > 20]


def _find_lexicon_matches(sentence: str, lexicon: set[str]) -> list[str]:
    s = sentence.lower()
    return sorted({term for term in lexicon if term in s})


def _has_phrase(sentence: str, phrases: list[re.Pattern[str]]) -> str | None:
    for pat in phrases:
        m = pat.search(sentence)
        if m:
            return m.group(0)
    return None


def _parse_penalty_usd(sentence: str) -> int | None:
    """Crude currency extraction; returns 0–9 digit USD-equivalent on best-effort basis.

    Treats $/USD as USD; flags EUR/GBP as approximate (1:1 for the demo).
    """
    m = PENALTY_RE.search(sentence)
    if not m:
        return None
    raw = m.group(1) or m.group(2)
    if not raw:
        return None
    try:
        amt = float(raw.replace(",", ""))
    except ValueError:
        return None
    return int(amt) if amt > 0 else None


def _find_license(sentence: str) -> str | None:
    s = sentence.lower()
    for hint in LICENSE_HINTS:
        if hint in s:
            return hint
    return None


def extract_rules_stub(
    text: str, *, country: str, source_doc: str, source_url: str
) -> list[dict]:
    """Filter sentences that contain a fisheries subject AND a rule signal.

    Three paths to qualify:
      1. (species OR gear) AND (prohibition OR penalty OR license)  — original
      2. general fishing term AND (prohibition OR penalty OR license)  — broader
      3. (zone OR season/closure term) AND (prohibition OR penalty OR license)
    """
    rules: list[dict] = []
    today = date.today().isoformat()
    for sentence in _split_sentences(text):
        species = _find_lexicon_matches(sentence, SPECIES)
        gear = _find_lexicon_matches(sentence, GEAR)
        zone = _find_lexicon_matches(sentence, ZONE)
        general = _find_lexicon_matches(sentence, FISHING_GENERAL)
        season = _find_lexicon_matches(sentence, SEASON_CLOSURE)
        prohibition = _has_phrase(sentence, PROHIBITION_PHRASES)
        penalty_usd = _parse_penalty_usd(sentence)
        license_hint = _find_license(sentence)

        has_rule = bool(prohibition or penalty_usd or license_hint)
        if not has_rule:
            continue

        has_specific_subject = bool(species or gear)
        has_general_subject = bool(general)
        has_zone_or_season = bool(zone or season)

        if not (has_specific_subject or has_general_subject or has_zone_or_season):
            continue

        # Assign confidence based on how specific the match is.
        if has_specific_subject:
            confidence = "silver"
        elif has_zone_or_season:
            confidence = "silver"
        else:
            confidence = "bronze"  # general fishing term only

        rules.append({
            "country": country.upper(),
            "source_doc": source_doc,
            "source_url": source_url,
            "source_sentence": sentence,
            "species": species,
            "gear": gear,
            "zone": zone,
            "prohibition": prohibition or "",
            "penalty_usd": penalty_usd,
            "license": license_hint or "",
            "confidence": confidence,
            "extracted_at": today,
        })
    return rules


def extract_rules_ner(text: str, *, country: str, source_doc: str, source_url: str) -> list[dict]:
    """NER mode: requires fine-tuned weights at finetune/artifacts/legal_bert_ner/."""
    from backend.services.legal_extractor import extract_rules as _ner_extract  # type: ignore
    return _ner_extract(text=text, country=country, source_doc=source_doc, source_url=source_url)


def iter_raw_docs(countries: Iterable[str]) -> Iterable[tuple[str, dict]]:
    for iso3 in countries:
        country_dir = RAW_DIR / iso3.upper()
        if not country_dir.exists():
            continue
        for json_file in sorted(country_dir.glob("*.json")):
            try:
                yield iso3.upper(), json.loads(json_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract rule tuples from fetched FAOLEX docs.")
    parser.add_argument("--countries", nargs="+",
                        default=["ECU", "PHL", "ESP", "CHN", "IDN"])
    parser.add_argument("--mode", choices=["stub", "ner"], default="stub")
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    extractor = extract_rules_stub if args.mode == "stub" else extract_rules_ner

    args.out.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with args.out.open("w", encoding="utf-8") as f:
        for country, doc in iter_raw_docs(args.countries):
            text = doc.get("text") or doc.get("abstract") or ""
            if not text:
                continue
            rules = extractor(
                text=text,
                country=country,
                source_doc=doc.get("id", "unknown"),
                source_url=doc.get("url", ""),
            )
            for r in rules:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                total += 1

    print(f"Wrote {total} tuple(s) to {args.out} ({args.mode} mode).")


if __name__ == "__main__":
    main()
