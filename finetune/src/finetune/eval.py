"""seqeval F1 per label for the trained legal-NER model.

Usage:
    python -m finetune.eval
    python -m finetune.eval --weights finetune/artifacts/legal_bert_ner

A held-out F1 ≥ 0.6 is the threshold for "useful" — silver labels are noisy,
so don't expect 0.9. If F1 < 0.5 across the board, fall back to stub-mode
extraction for the demo.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch
from seqeval.metrics import classification_report
from transformers import (
    AutoModelForTokenClassification,
    AutoTokenizer,
    DataCollatorForTokenClassification,
    Trainer,
)

from finetune.dataset import DEFAULT_LABELS_PATH, ID_TO_LABEL, build_datasets

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "artifacts" / "legal_bert_ner"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the fine-tuned legal-NER model.")
    parser.add_argument("--weights", type=Path, default=ARTIFACT_DIR)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_PATH)
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.weights)
    model = AutoModelForTokenClassification.from_pretrained(args.weights)

    _, val_ds = build_datasets(tokenizer, labels_path=args.labels)

    trainer = Trainer(
        model=model,
        tokenizer=tokenizer,
        data_collator=DataCollatorForTokenClassification(tokenizer),
    )
    output = trainer.predict(val_ds)
    preds = np.argmax(output.predictions, axis=-1)
    labels = output.label_ids

    pred_seqs: list[list[str]] = []
    true_seqs: list[list[str]] = []
    for pred_row, label_row in zip(preds, labels):
        pred_tags: list[str] = []
        true_tags: list[str] = []
        for pred_id, label_id in zip(pred_row, label_row):
            if label_id == -100:
                continue
            pred_tags.append(ID_TO_LABEL[int(pred_id)])
            true_tags.append(ID_TO_LABEL[int(label_id)])
        if true_tags:
            pred_seqs.append(pred_tags)
            true_seqs.append(true_tags)

    print(classification_report(true_seqs, pred_seqs, digits=3, zero_division=0))


if __name__ == "__main__":
    main()
