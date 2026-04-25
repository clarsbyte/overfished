"""Fine-tune nlpaueb/legal-bert-base-uncased for token classification on silver labels.

Two regularization paths (BERT-base on ~300 sentences benefits from at least one):
  Default: freeze embeddings + bottom 6 transformer layers; train top 6 + classifier.
           Standard, simple, no extra dep.
  --lora:  PEFT LoRA on attention query/value projections (r=8, alpha=16).
           Smaller checkpoint, mild quality dip at this scale; needs the
           `[lora]` extras: pip install -e .[lora]

CLI:
  python -m finetune.train                              # full training run
  python -m finetune.train --lora                       # LoRA path
  python -m finetune.train --dry-run --device cpu       # 5-step wiring smoke test
  python -m finetune.train --epochs 3 --batch-size 8    # tune
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch
from transformers import (
    AutoModelForTokenClassification,
    AutoTokenizer,
    DataCollatorForTokenClassification,
    Trainer,
    TrainingArguments,
)

from finetune.dataset import (
    DEFAULT_LABELS_PATH,
    ID_TO_LABEL,
    LABEL_TO_ID,
    LABELS,
    build_datasets,
)

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "artifacts" / "legal_bert_ner"
BASE_MODEL = "nlpaueb/legal-bert-base-uncased"


def freeze_lower_layers(model, num_to_freeze: int = 6) -> None:
    """Freeze embeddings + the lowest N transformer encoder layers.

    On a tiny silver dataset this acts as a strong regularizer — equivalent
    in spirit to LoRA's lower-rank update, but with no extra dependency.
    """
    encoder = getattr(model, "bert", None) or getattr(model, "base_model", None)
    if encoder is None:
        print("  [warn] unexpected model layout — skipping layer freeze")
        return
    for param in encoder.embeddings.parameters():
        param.requires_grad = False
    for layer in encoder.encoder.layer[:num_to_freeze]:
        for param in layer.parameters():
            param.requires_grad = False
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"  [freeze] embeddings + bottom {num_to_freeze} layers frozen — "
          f"trainable {trainable/1e6:.1f}M / {total/1e6:.1f}M params")


def apply_lora(model):
    try:
        from peft import LoraConfig, TaskType, get_peft_model
    except ImportError as exc:
        raise SystemExit(
            "peft is not installed. Install with: pip install -e .[lora]"
        ) from exc
    config = LoraConfig(
        task_type=TaskType.TOKEN_CLS,
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=["query", "value"],
    )
    model = get_peft_model(model, config)
    model.print_trainable_parameters()
    return model


def compute_metrics(eval_pred):
    """Macro F1 over non-pad positions; per-label breakdown is in eval.py."""
    predictions, labels = eval_pred
    preds = np.argmax(predictions, axis=-1)
    mask = labels != -100
    correct = ((preds == labels) & mask).sum()
    total = mask.sum()
    return {"accuracy": float(correct) / float(total) if total else 0.0}


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune LegalBERT on silver NER labels.")
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_PATH)
    parser.add_argument("--output", type=Path, default=ARTIFACT_DIR)
    parser.add_argument("--base-model", default=BASE_MODEL)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=3e-5)
    parser.add_argument("--lora", action="store_true",
                        help="use PEFT LoRA instead of frozen-lower-layers regularization")
    parser.add_argument("--freeze-layers", type=int, default=6,
                        help="number of bottom encoder layers to freeze (default 6, ignored with --lora)")
    parser.add_argument("--dry-run", action="store_true",
                        help="run only 5 steps for wiring verification")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    args = parser.parse_args()

    use_cuda = (args.device == "cuda") or (args.device == "auto" and torch.cuda.is_available())
    use_fp16 = use_cuda and not args.dry_run

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    model = AutoModelForTokenClassification.from_pretrained(
        args.base_model,
        num_labels=len(LABELS),
        id2label=ID_TO_LABEL,
        label2id=LABEL_TO_ID,
    )

    if args.lora:
        model = apply_lora(model)
    elif args.freeze_layers > 0:
        freeze_lower_layers(model, num_to_freeze=args.freeze_layers)

    train_ds, val_ds = build_datasets(tokenizer, labels_path=args.labels)
    print(f"  [data] train={len(train_ds)} val={len(val_ds)}")

    args.output.mkdir(parents=True, exist_ok=True)
    training_args = TrainingArguments(
        output_dir=str(args.output),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        warmup_ratio=0.1,
        weight_decay=0.01,
        fp16=use_fp16,
        logging_steps=10,
        save_strategy="epoch",
        eval_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="accuracy",
        report_to=[],
        max_steps=5 if args.dry_run else -1,
        no_cuda=not use_cuda,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        tokenizer=tokenizer,
        data_collator=DataCollatorForTokenClassification(tokenizer),
        compute_metrics=compute_metrics,
    )

    trainer.train()
    trainer.save_model(str(args.output))
    tokenizer.save_pretrained(str(args.output))
    print(f"\nDone. Weights saved to {args.output}")
    print("Next: python -m finetune.eval")


if __name__ == "__main__":
    main()
