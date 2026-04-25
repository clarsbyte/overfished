"""Silver-label FAOLEX sentences with Claude → BIO tags for legal-NER fine-tuning.

The few-shot block is large (~4-5K tokens) and identical across every request,
so we put it in the cached `system` array and pay the full-price write once;
every subsequent sentence reads the cache at ~10x discount. With ~300 sentences
this turns a $30 labeling pass into ~$3.

Output JSONL schema (one object per labeled sentence):
  {
    "doc_id":  "LEX-FAOC-...",
    "country": "ECU",
    "tokens":  ["The", "use", "of", "purse", "seines", "...", "."],
    "labels":  ["O",  "O",  "O", "B-GEAR", "I-GEAR", "...", "O"],
    "source":  "claude-opus-4-7"
  }

CLI:
    python -m finetune.auto_label --countries ECU --limit 5     # dry-run
    python -m finetune.auto_label                               # full pass
    python -m finetune.auto_label --max-sentences 300           # cap output
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
OUT_PATH = ROOT / "data" / "silver" / "labels.jsonl"

MODEL = "claude-opus-4-7"

LABELS = [
    "O",
    "B-SPECIES", "I-SPECIES",
    "B-GEAR", "I-GEAR",
    "B-ZONE", "I-ZONE",
    "B-PENALTY", "I-PENALTY",
    "B-PROHIBITION", "I-PROHIBITION",
    "B-LICENSE", "I-LICENSE",
]

SYSTEM_PROMPT = """You are a legal-NER annotator labeling sentences from FAOLEX
fisheries-law documents. Your output trains a token classifier (LegalBERT) for
downstream rule extraction.

LABEL SET (BIO scheme):
  O               outside any entity
  B-SPECIES       beginning of a fish/marine-species mention (bluefin tuna, hammerhead shark, sea cucumber, octopus)
  I-SPECIES       continuation of a species mention
  B-GEAR          beginning of a fishing gear or method (purse seine, longline, gillnet, trawl, dredge, FAD)
  I-GEAR          continuation of a gear mention
  B-ZONE          beginning of a fishing area / regulatory zone (EEZ, marine reserve, no-take zone, territorial sea, MPA)
  I-ZONE          continuation of a zone mention
  B-PENALTY       beginning of a penalty clause / monetary fine (USD 50,000 / a fine not exceeding $10,000 / EUR 5,000)
  I-PENALTY       continuation of a penalty
  B-PROHIBITION   beginning of a prohibition phrase ("shall not", "is prohibited", "are forbidden", "no person shall")
  I-PROHIBITION   continuation of a prohibition phrase
  B-LICENSE       beginning of a license/permit requirement ("a license issued by", "permit required", "shall hold an authorization")
  I-LICENSE       continuation of a license requirement

RULES:
  1. Output exactly one label per input token, in order. Do NOT add, drop, or reorder tokens.
  2. Use B- only on the FIRST token of an entity span; I- on every subsequent token within that span.
  3. A new entity (even of the same type) restarts with B-.
  4. Punctuation that is NOT part of an entity gets O.
  5. When uncertain, prefer O over a wrong label — silver labels train a denoising student, not a perfect oracle.
  6. Do not invent entities not present in the sentence.

EXAMPLES (input is whitespace-tokenized; output is the parallel label list):

Example 1
  Tokens: ["The", "use", "of", "purse", "seines", "for", "catching", "bluefin", "tuna", "is", "prohibited", "in", "the", "Mediterranean", "Sea", "."]
  Labels: ["O",   "O",   "O",  "B-GEAR","I-GEAR","O",  "O",        "B-SPECIES","I-SPECIES","O","B-PROHIBITION","O","O","B-ZONE","I-ZONE","O"]

Example 2
  Tokens: ["Industrial", "trawling", "within", "marine", "reserves", "shall", "not", "be", "permitted", ";", "violators", "face", "penalties", "of", "up", "to", "USD", "50,000", "."]
  Labels: ["O",         "B-GEAR",   "O",      "B-ZONE","I-ZONE",   "B-PROHIBITION","I-PROHIBITION","O","O","O","O","O","O","O","O","O","B-PENALTY","I-PENALTY","O"]

Example 3
  Tokens: ["Longline", "fishing", "for", "swordfish", "requires", "a", "license", "issued", "by", "the", "Ministry", "of", "Fisheries", "."]
  Labels: ["B-GEAR",   "O",      "O",   "B-SPECIES","O",        "O","B-LICENSE","I-LICENSE","I-LICENSE","O","O","O","O","O"]

Example 4
  Tokens: ["No", "person", "shall", "engage", "in", "fishing", "for", "sea", "cucumber", "in", "the", "Galápagos", "Marine", "Reserve", "without", "prior", "authorization", "."]
  Labels: ["B-PROHIBITION","I-PROHIBITION","I-PROHIBITION","O","O","O","O","B-SPECIES","I-SPECIES","O","O","B-ZONE","I-ZONE","I-ZONE","O","B-LICENSE","I-LICENSE","O"]

Example 5
  Tokens: ["The", "Coastal", "Authority", "shall", "publish", "quarterly", "reports", "on", "stock", "assessments", "."]
  Labels: ["O",   "O",       "O",         "O",     "O",       "O",          "O",       "O", "O",     "O",            "O"]

OUTPUT FORMAT:
Return JSON `{"labels": [...]}` where the list length exactly matches the
input tokens. If you cannot label confidently, return all "O" — do NOT refuse.
"""


class TokenLabels(BaseModel):
    labels: list[str] = Field(..., description="One BIO label per input token, in order.")


def whitespace_tokenize(sentence: str) -> list[str]:
    """Light tokenizer aligned with Claude's expected output format.

    Splits on whitespace, then peels punctuation off the ends so that ',', '.',
    ';', etc. become their own tokens — matches how the few-shot examples
    above are tokenized.
    """
    out: list[str] = []
    for word in sentence.strip().split():
        match = re.match(r"^(\W*)(.*?)(\W*)$", word, re.UNICODE)
        if not match:
            out.append(word)
            continue
        leading, core, trailing = match.groups()
        for ch in leading:
            out.append(ch)
        if core:
            out.append(core)
        for ch in trailing:
            out.append(ch)
    return [t for t in out if t]


def split_sentences(text: str) -> list[str]:
    """Same lightweight splitter used by extract_corpus, kept local to avoid
    a backend.* import from the offline pipeline."""
    text = re.sub(r"\s+", " ", text)
    abbrev = re.compile(r"(Art|Arts|No|Sec|Cap|cf|e\.g|i\.e|Mr|Ms|St)\.\s")
    sep = "\x00"
    text = abbrev.sub(lambda m: m.group(0).replace(".", sep), text)
    parts = re.split(r"(?<=[.?!])\s+(?=[A-ZÀ-ſ0-9])", text)
    return [p.replace(sep, ".").strip() for p in parts if 20 < len(p.strip()) < 600]


def iter_sentences(countries: Iterable[str]) -> Iterable[tuple[str, str, str]]:
    for iso3 in countries:
        country_dir = RAW_DIR / iso3.upper()
        if not country_dir.exists():
            continue
        for json_file in sorted(country_dir.glob("*.json")):
            try:
                doc = json.loads(json_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            text = doc.get("text") or doc.get("abstract") or ""
            doc_id = doc.get("id", json_file.stem)
            for sent in split_sentences(text):
                yield iso3.upper(), doc_id, sent


def label_sentence(client: anthropic.Anthropic, tokens: list[str]) -> list[str] | None:
    """Single round-trip with prompt caching on the system block."""
    user_payload = json.dumps({"tokens": tokens}, ensure_ascii=False)
    try:
        response = client.messages.parse(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_payload}],
            output_format=TokenLabels,
        )
    except anthropic.APIError as exc:
        print(f"  [api error] {exc!s}", file=sys.stderr)
        return None

    parsed = response.parsed_output
    if parsed is None:
        return None
    if len(parsed.labels) != len(tokens):
        print(
            f"  [skip] label count mismatch: {len(parsed.labels)} labels vs {len(tokens)} tokens",
            file=sys.stderr,
        )
        return None
    if any(label not in LABELS for label in parsed.labels):
        unknowns = sorted({label for label in parsed.labels if label not in LABELS})
        print(f"  [skip] unknown labels: {unknowns}", file=sys.stderr)
        return None
    return parsed.labels


def main() -> None:
    parser = argparse.ArgumentParser(description="Silver-label FAOLEX sentences with Claude.")
    parser.add_argument("--countries", nargs="+",
                        default=["ECU", "PHL", "ESP", "CHN", "IDN"])
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument("--limit", type=int, default=0,
                        help="dry-run: stop after N labeled sentences (0 = no limit)")
    parser.add_argument("--max-sentences", type=int, default=300,
                        help="hard cap on the number of sentences to label (default 300)")
    args = parser.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Set it in finetune/.env or your shell.")

    client = anthropic.Anthropic()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    cap = args.limit if args.limit > 0 else args.max_sentences
    written = 0
    cache_writes = 0
    cache_reads = 0

    with args.out.open("w", encoding="utf-8") as f:
        for country, doc_id, sentence in iter_sentences(args.countries):
            if written >= cap:
                break
            tokens = whitespace_tokenize(sentence)
            if not (3 <= len(tokens) <= 80):
                continue

            labels = label_sentence(client, tokens)
            if labels is None:
                continue

            f.write(json.dumps({
                "doc_id": doc_id,
                "country": country,
                "tokens": tokens,
                "labels": labels,
                "source": MODEL,
            }, ensure_ascii=False) + "\n")
            written += 1

            # The Anthropic SDK doesn't surface usage via parse() directly on
            # the parsed_output, but the response object carries it. We don't
            # plumb it through the helper to keep the path simple — verify
            # cache hits with a sample inspection: re-run with `--limit 5` and
            # check ANTHROPIC_LOG=info output.

            if written % 25 == 0:
                print(f"  [{written}/{cap}] {country} {doc_id}: labeled")

    print(f"\nDone. Wrote {written} labeled sentence(s) to {args.out}")
    print("Tip: set ANTHROPIC_LOG=info to verify cache_read_input_tokens > 0 after the first request.")


if __name__ == "__main__":
    main()
