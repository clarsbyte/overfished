"""NER-mode rule extractor — loads the fine-tuned LegalBERT weights.

This module is the runtime counterpart to finetune/src/finetune/extract_corpus.py
in --mode ner. It's kept in backend/ (not finetune/) so the agent could call
it at request time if we ever want live extraction over fresh FAOLEX text;
the offline pipeline imports it lazily.

Until `python -m finetune.train` produces weights at
finetune/artifacts/legal_bert_ner/, this raises a clear error pointing at
stub mode.

Output schema matches the stub extractor exactly so build_index.py is mode-agnostic.
"""

from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from pathlib import Path

WEIGHTS_DIR = Path(__file__).resolve().parents[2] / "finetune" / "artifacts" / "legal_bert_ner"

# Same lightweight currency parser used by the stub extractor.
PENALTY_RE = re.compile(
    r"(?:US\$?|USD|EUR|GBP|\$|€|£)\s*([\d,]+(?:\.\d+)?)"
    r"|"
    r"([\d,]+(?:\.\d+)?)\s*(?:US\s*)?dollars?\b",
    re.IGNORECASE,
)


def _split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text)
    abbrev = re.compile(r"(Art|Arts|No|Sec|Cap|cf|e\.g|i\.e|Mr|Ms|St)\.\s")
    sep = "\x00"
    text = abbrev.sub(lambda m: m.group(0).replace(".", sep), text)
    parts = re.split(r"(?<=[.?!])\s+(?=[A-ZÀ-ſ0-9])", text)
    return [p.replace(sep, ".").strip() for p in parts if 20 < len(p.strip()) < 600]


@lru_cache(maxsize=1)
def _load_pipeline():
    if not WEIGHTS_DIR.exists():
        raise RuntimeError(
            f"Fine-tuned weights not found at {WEIGHTS_DIR}. "
            "Run `python -m finetune.train` first, or use --mode stub."
        )
    try:
        from transformers import (  # type: ignore
            AutoModelForTokenClassification,
            AutoTokenizer,
            pipeline,
        )
    except ImportError as exc:
        raise RuntimeError(
            "transformers is not installed. Install with: "
            "pip install -r backend/requirements-rag.txt"
        ) from exc

    tokenizer = AutoTokenizer.from_pretrained(WEIGHTS_DIR)
    model = AutoModelForTokenClassification.from_pretrained(WEIGHTS_DIR)
    return pipeline(
        "token-classification",
        model=model,
        tokenizer=tokenizer,
        aggregation_strategy="simple",
    )


def _parse_penalty_usd(sentence: str) -> int | None:
    match = PENALTY_RE.search(sentence)
    if not match:
        return None
    raw = match.group(1) or match.group(2)
    try:
        amt = float(raw.replace(",", ""))
    except (TypeError, ValueError):
        return None
    return int(amt) if amt > 0 else None


def _entities_to_rule(
    entities: list[dict],
    sentence: str,
    *,
    country: str,
    source_doc: str,
    source_url: str,
) -> dict | None:
    """Turn a sentence's entity spans into a rule tuple matching stub-mode shape."""
    by_label: dict[str, list[str]] = {}
    for ent in entities:
        label = ent.get("entity_group") or ent.get("entity") or ""
        word = (ent.get("word") or "").strip()
        if not label or not word:
            continue
        by_label.setdefault(label, []).append(word)

    has_subject = bool(by_label.get("SPECIES") or by_label.get("GEAR"))
    has_rule = bool(
        by_label.get("PROHIBITION") or by_label.get("PENALTY") or by_label.get("LICENSE")
    )
    if not (has_subject and has_rule):
        return None

    return {
        "country": country.upper(),
        "source_doc": source_doc,
        "source_url": source_url,
        "source_sentence": sentence,
        "species": sorted({w.lower() for w in by_label.get("SPECIES", [])}),
        "gear": sorted({w.lower() for w in by_label.get("GEAR", [])}),
        "zone": sorted({w.lower() for w in by_label.get("ZONE", [])}),
        "prohibition": " ".join(by_label.get("PROHIBITION", [])),
        "penalty_usd": _parse_penalty_usd(sentence),
        "license": " ".join(by_label.get("LICENSE", [])),
        "confidence": "silver",
        "extracted_at": date.today().isoformat(),
    }


def extract_rules(
    text: str, *, country: str, source_doc: str, source_url: str
) -> list[dict]:
    """Run NER per sentence; emit rule tuples for sentences that pair a
    subject (SPECIES/GEAR) with a rule signal (PROHIBITION/PENALTY/LICENSE)."""
    ner = _load_pipeline()
    rules: list[dict] = []
    for sentence in _split_sentences(text):
        entities = ner(sentence)
        rule = _entities_to_rule(
            entities, sentence,
            country=country, source_doc=source_doc, source_url=source_url,
        )
        if rule:
            rules.append(rule)
    return rules
