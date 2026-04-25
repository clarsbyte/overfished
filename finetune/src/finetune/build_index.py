"""Read extracted_rules.jsonl → upsert into the Qdrant collection used by the agent.

Calls `init_collection()` first (recreates), so this is idempotent: re-running
gives a clean rebuild from the current jsonl.

Usage:
    python -m finetune.build_index
    python -m finetune.build_index --in finetune/data/extracted_rules.jsonl
    python -m finetune.build_index --model sentence-transformers/all-mpnet-base-v2

The agent process reads the resulting Qdrant store at backend/data/qdrant_db/.
Restart the agent after a rebuild — local-mode Qdrant uses a single-writer file
lock, so the agent must reopen its read handle.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# Make backend.services importable. Backend uses a flat layout (no
# top-level __init__.py), so we add the backend dir directly.
ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.legal_vectorstore import (  # noqa: E402
    DEFAULT_EMBED_MODEL,
    index_rules,
    init_collection,
    collection_count,
)

DEFAULT_INPUT = ROOT / "finetune" / "data" / "extracted_rules.jsonl"


def _load_rules(path: Path) -> list[dict]:
    rules: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rules.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rules


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Qdrant index from extracted rules.")
    parser.add_argument("--in", dest="input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--model", default=DEFAULT_EMBED_MODEL,
                        help="sentence-transformers model name (default: law-ai/InLegalBERT)")
    args = parser.parse_args()

    if not args.input.exists():
        sys.exit(f"input not found: {args.input}\nRun `python -m finetune.extract_corpus` first.")

    rules = _load_rules(args.input)
    if not rules:
        sys.exit(f"input is empty: {args.input}")

    init_collection()

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for rule in rules:
        country = (rule.get("country") or "UNKNOWN").upper()
        doc_id = rule.get("source_doc") or "unknown"
        grouped[(country, doc_id)].append(rule)

    total = 0
    for (country, doc_id), group in grouped.items():
        n = index_rules(group, country=country, doc_id=doc_id, model_name=args.model)
        total += n
        print(f"  [{country}] {doc_id}: indexed {n} rule(s)")

    print(f"\nDone. Indexed {total} rule(s) across {len(grouped)} document(s).")
    print(f"Collection size: {collection_count()}")


if __name__ == "__main__":
    main()
