"""JSONL silver labels → HuggingFace Dataset for token classification.

The classic gotcha: BERT-family tokenizers split words into subwords, but our
labels are at the word level. We align by:
  1. tokenizing with is_split_into_words=True
  2. mapping each subword back via word_ids()
  3. labeling only the FIRST subword of each word; setting -100 for the rest
     (loss is ignored at -100, so subword positions don't pull gradient)
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from datasets import Dataset
from transformers import PreTrainedTokenizerBase

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LABELS_PATH = ROOT / "data" / "silver" / "labels.jsonl"

LABELS = [
    "O",
    "B-SPECIES", "I-SPECIES",
    "B-GEAR", "I-GEAR",
    "B-ZONE", "I-ZONE",
    "B-PENALTY", "I-PENALTY",
    "B-PROHIBITION", "I-PROHIBITION",
    "B-LICENSE", "I-LICENSE",
]
LABEL_TO_ID = {label: i for i, label in enumerate(LABELS)}
ID_TO_LABEL = {i: label for i, label in enumerate(LABELS)}


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            tokens = row.get("tokens") or []
            labels = row.get("labels") or []
            if len(tokens) != len(labels):
                continue
            if any(label not in LABEL_TO_ID for label in labels):
                continue
            rows.append({"tokens": tokens, "labels": labels})
    return rows


def build_datasets(
    tokenizer: PreTrainedTokenizerBase,
    *,
    labels_path: Path = DEFAULT_LABELS_PATH,
    val_ratio: float = 0.2,
    seed: int = 42,
    max_length: int = 256,
) -> tuple[Dataset, Dataset]:
    rows = _load_jsonl(labels_path)
    if not rows:
        raise RuntimeError(
            f"No usable rows in {labels_path}. "
            "Run `python -m finetune.auto_label` first."
        )

    random.Random(seed).shuffle(rows)
    n_val = max(1, int(len(rows) * val_ratio))
    train_rows = rows[n_val:]
    val_rows = rows[:n_val]

    def to_hf(rows_subset: list[dict]) -> Dataset:
        return Dataset.from_dict({
            "tokens": [r["tokens"] for r in rows_subset],
            "ner_tags": [[LABEL_TO_ID[label] for label in r["labels"]] for r in rows_subset],
        })

    train_ds = to_hf(train_rows)
    val_ds = to_hf(val_rows)

    def tokenize_and_align(examples: dict) -> dict:
        tokenized = tokenizer(
            examples["tokens"],
            is_split_into_words=True,
            truncation=True,
            max_length=max_length,
        )
        all_aligned: list[list[int]] = []
        for batch_idx, tag_seq in enumerate(examples["ner_tags"]):
            word_ids = tokenized.word_ids(batch_index=batch_idx)
            aligned: list[int] = []
            previous_word = None
            for word_id in word_ids:
                if word_id is None:
                    aligned.append(-100)
                elif word_id != previous_word:
                    aligned.append(tag_seq[word_id])
                else:
                    aligned.append(-100)
                previous_word = word_id
            all_aligned.append(aligned)
        tokenized["labels"] = all_aligned
        return tokenized

    train_ds = train_ds.map(tokenize_and_align, batched=True, remove_columns=["tokens", "ner_tags"])
    val_ds = val_ds.map(tokenize_and_align, batched=True, remove_columns=["tokens", "ner_tags"])
    return train_ds, val_ds
