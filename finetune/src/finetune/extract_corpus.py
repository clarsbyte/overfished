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

# Lexicons cover the fisheries-law vocabulary the user's demo countries care
# about. These are intentionally short — false positives are cheaper than
# false negatives at the demo stage; the NER mode will fix recall.
SPECIES = {
    "tuna", "yellowfin", "bigeye", "skipjack", "bluefin", "albacore",
    "shark", "hammerhead", "ray", "manta",
    "swordfish", "marlin", "sailfish",
    "sardine", "anchovy", "mackerel", "herring",
    "cod", "haddock", "pollock",
    "octopus", "squid", "cuttlefish",
    "lobster", "crab", "shrimp", "prawn",
    "grouper", "snapper", "rockfish",
    "salmon", "trout",
    "sea cucumber", "abalone", "scallop",
    "eel", "hake",
}
GEAR = {
    "trawl", "trawler", "trawling",
    "longline", "long-line", "long line",
    "gillnet", "gill net", "drift net", "driftnet",
    "purse seine", "seine net", "seiner",
    "dredge", "dredging",
    "fad", "fish aggregating device",
    "harpoon",
    "trap", "pot",
    "hook and line",
    "bottom trawl", "midwater trawl",
    "pole and line",
}
ZONE = {
    "eez", "exclusive economic zone",
    "territorial sea", "territorial waters",
    "marine reserve", "marine protected area", "mpa",
    "no-take", "no take zone",
    "marine sanctuary",
    "high seas",
    "coastal zone",
}
LICENSE_HINTS = {
    "license required", "licence required",
    "permit required",
    "authorization required", "authorisation required",
    "subject to license", "subject to permit",
    "shall hold a license", "shall hold a permit",
    "with prior authorization", "with prior authorisation",
}
PROHIBITION_PHRASES = [
    re.compile(r"\bshall not\b", re.IGNORECASE),
    re.compile(r"\bis prohibited\b", re.IGNORECASE),
    re.compile(r"\bare prohibited\b", re.IGNORECASE),
    re.compile(r"\bforbidden\b", re.IGNORECASE),
    re.compile(r"\bbanned\b", re.IGNORECASE),
    re.compile(r"\bnot permitted\b", re.IGNORECASE),
    re.compile(r"\bunlawful\b", re.IGNORECASE),
    re.compile(r"\bno person shall\b", re.IGNORECASE),
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
    """Filter sentences with both a subject (species/gear) AND a rule signal."""
    rules: list[dict] = []
    today = date.today().isoformat()
    for sentence in _split_sentences(text):
        species = _find_lexicon_matches(sentence, SPECIES)
        gear = _find_lexicon_matches(sentence, GEAR)
        zone = _find_lexicon_matches(sentence, ZONE)
        prohibition = _has_phrase(sentence, PROHIBITION_PHRASES)
        penalty_usd = _parse_penalty_usd(sentence)
        license_hint = _find_license(sentence)

        has_subject = bool(species or gear)
        has_rule = bool(prohibition or penalty_usd or license_hint)
        if not (has_subject and has_rule):
            continue

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
            "confidence": "silver",
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
