"""Training and evaluation routines for sequence classifiers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import torch
from torch import Tensor, nn
from torch.utils.data import DataLoader

from .dataset import SequenceDatasetBundle, collate_sequence_batch, prepare_sequence_datasets
from .metrics import classification_metrics, ensemble_probabilities
from .models import ModelType, SequenceModelConfig, build_model


@dataclass(frozen=True)
class TrainingConfig:
    """Configuration for RNN/BiLSTM sequence training."""

    seq_len: int = 8
    stride: int = 1
    val_fraction: float = 0.2
    batch_size: int = 16
    epochs: int = 5
    learning_rate: float = 1e-3
    hidden_dim: int = 64
    num_layers: int = 1
    dropout: float = 0.1
    top_k: int = 3
    device: str = "cpu"
    checkpoint_dir: str | None = None


@dataclass(frozen=True)
class ModelTrainingResult:
    """Outputs for one trained model."""

    model_type: ModelType
    best_val_loss: float
    metrics: dict[str, float]
    checkpoint_path: str | None
    model: nn.Module
    val_logits: Tensor
    val_targets: Tensor
    val_probabilities: Tensor


@dataclass(frozen=True)
class TrainingComparisonResult:
    """Joint training outputs for both model families."""

    dataset_bundle: SequenceDatasetBundle
    rnn_result: ModelTrainingResult
    bilstm_result: ModelTrainingResult
    ensemble_metrics: dict[str, float] | None
    selected_model_type: str


def train_and_compare_models(
    dataframe: pd.DataFrame,
    *,
    config: TrainingConfig,
    feature_columns: list[str] | None = None,
) -> TrainingComparisonResult:
    """Prepare datasets, train both model types, and compare results."""
    bundle = prepare_sequence_datasets(
        dataframe,
        seq_len=config.seq_len,
        stride=config.stride,
        val_fraction=config.val_fraction,
        feature_columns=feature_columns,
    )

    rnn_result = train_sequence_model("rnn", bundle, config=config)
    bilstm_result = train_sequence_model("bilstm", bundle, config=config)

    ensemble_metrics: dict[str, float] | None = None
    selected_model_type = "bilstm" if bilstm_result.metrics["top1_accuracy"] >= rnn_result.metrics["top1_accuracy"] else "rnn"
    if rnn_result.val_probabilities.numel() and bilstm_result.val_probabilities.numel():
        ensemble_probs = ensemble_probabilities(
            [rnn_result.val_probabilities, bilstm_result.val_probabilities]
        )
        ensemble_logits = torch.log(ensemble_probs.clamp(min=1e-12))
        ensemble_metrics = classification_metrics(
            ensemble_logits,
            rnn_result.val_targets,
            top_k=config.top_k,
        )
        best_single = max(rnn_result.metrics["top1_accuracy"], bilstm_result.metrics["top1_accuracy"])
        if ensemble_metrics["top1_accuracy"] >= best_single:
            selected_model_type = "ensemble"

    return TrainingComparisonResult(
        dataset_bundle=bundle,
        rnn_result=rnn_result,
        bilstm_result=bilstm_result,
        ensemble_metrics=ensemble_metrics,
        selected_model_type=selected_model_type,
    )


def train_sequence_model(
    model_type: ModelType,
    bundle: SequenceDatasetBundle,
    *,
    config: TrainingConfig,
) -> ModelTrainingResult:
    """Train one model family and return best metrics/checkpoint."""
    device = torch.device(config.device)
    model_config = SequenceModelConfig(
        input_dim=bundle.input_dim,
        hidden_dim=config.hidden_dim,
        num_classes=len(bundle.class_to_mmsi),
        num_layers=config.num_layers,
        dropout=config.dropout,
    )
    model = build_model(model_type, model_config).to(device)

    train_loader = DataLoader(
        bundle.train_dataset,
        batch_size=config.batch_size,
        shuffle=True,
        collate_fn=collate_sequence_batch,
    )
    val_loader = DataLoader(
        bundle.val_dataset,
        batch_size=config.batch_size,
        shuffle=False,
        collate_fn=collate_sequence_batch,
    )

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    best_val_loss = float("inf")
    best_state = model.state_dict()

    for _ in range(config.epochs):
        model.train()
        for batch in train_loader:
            features = batch.features.to(device)
            lengths = batch.lengths.to(device)
            targets = batch.targets.to(device)
            optimizer.zero_grad()
            logits = model(features, lengths)
            loss = criterion(logits, targets)
            loss.backward()
            optimizer.step()

        val_loss = _compute_loss(model, val_loader, criterion, device)
        if val_loss <= best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    model.load_state_dict(best_state)
    model = model.to(device)
    logits, targets = _collect_logits_targets(model, val_loader, device)
    probabilities = torch.softmax(logits, dim=1) if logits.numel() else torch.empty((0, 0))
    metrics = (
        classification_metrics(logits, targets, top_k=config.top_k)
        if logits.numel()
        else {"top1_accuracy": 0.0, "topk_accuracy": 0.0, "brier_score": 0.0, "ece": 0.0}
    )

    checkpoint_path = _maybe_save_checkpoint(model_type, best_state, bundle, config)
    return ModelTrainingResult(
        model_type=model_type,
        best_val_loss=best_val_loss if best_val_loss < float("inf") else 0.0,
        metrics=metrics,
        checkpoint_path=checkpoint_path,
        model=model,
        val_logits=logits,
        val_targets=targets,
        val_probabilities=probabilities,
    )


def _compute_loss(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> float:
    model.eval()
    losses: list[float] = []
    with torch.no_grad():
        for batch in loader:
            features = batch.features.to(device)
            lengths = batch.lengths.to(device)
            targets = batch.targets.to(device)
            logits = model(features, lengths)
            losses.append(float(criterion(logits, targets).item()))
    if not losses:
        return 0.0
    return sum(losses) / len(losses)


def _collect_logits_targets(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
) -> tuple[Tensor, Tensor]:
    model.eval()
    logits_parts: list[Tensor] = []
    targets_parts: list[Tensor] = []
    with torch.no_grad():
        for batch in loader:
            features = batch.features.to(device)
            lengths = batch.lengths.to(device)
            targets = batch.targets.to(device)
            logits = model(features, lengths)
            logits_parts.append(logits.cpu())
            targets_parts.append(targets.cpu())
    if not logits_parts:
        return torch.empty((0, 0)), torch.empty((0,), dtype=torch.long)
    return torch.cat(logits_parts, dim=0), torch.cat(targets_parts, dim=0)


def _maybe_save_checkpoint(
    model_type: ModelType,
    state_dict: dict[str, Tensor],
    bundle: SequenceDatasetBundle,
    config: TrainingConfig,
) -> str | None:
    if config.checkpoint_dir is None:
        return None
    checkpoint_dir = Path(config.checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    output_path = checkpoint_dir / f"{model_type}_sequence_model.pt"
    torch.save(
        {
            "model_state_dict": state_dict,
            "mmsi_to_class": bundle.mmsi_to_class,
            "class_to_mmsi": bundle.class_to_mmsi,
            "feature_columns": bundle.feature_columns,
            "config": config.__dict__,
        },
        output_path,
    )
    return str(output_path)
