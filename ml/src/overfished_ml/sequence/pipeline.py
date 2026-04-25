"""Pipeline helpers for sequence model scoring and assignment."""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import Tensor, nn

from .assignment import AssignmentResult, apply_confidence_threshold, softmax_with_temperature, topk_renormalize


@dataclass(frozen=True)
class SequenceBatch:
    """Batched padded sequence features."""

    features: Tensor
    lengths: Tensor


@dataclass(frozen=True)
class TopKMmsiPredictions:
    """Model output plus top-k MMSI candidates."""

    logits: Tensor
    probabilities: Tensor
    topk_indices: Tensor
    topk_mmsi: list[list[str]]
    topk_probabilities: Tensor
    assignment: AssignmentResult


def forward_scores(model: nn.Module, batch: SequenceBatch) -> tuple[Tensor, Tensor]:
    """Return logits and probabilities for a sequence batch."""
    logits = model(batch.features, batch.lengths)
    probabilities = softmax_with_temperature(logits, temperature=1.0)
    return logits, probabilities


def soft_assign_boats(
    logits: Tensor,
    *,
    temperature: float = 1.0,
    top_k: int | None = None,
    confidence_threshold: float | None = None,
) -> AssignmentResult:
    """Apply soft-assignment post-processing to model logits."""
    probabilities = softmax_with_temperature(logits, temperature=temperature)
    probabilities = topk_renormalize(probabilities, top_k=top_k)
    return apply_confidence_threshold(probabilities, confidence_threshold=confidence_threshold)


def predict_topk_mmsi(
    model: nn.Module,
    batch: SequenceBatch,
    *,
    class_to_mmsi: dict[int, str],
    temperature: float = 1.0,
    top_k: int = 3,
    confidence_threshold: float | None = None,
) -> TopKMmsiPredictions:
    """Run model inference and map top-k class IDs back to MMSI strings."""
    logits = model(batch.features, batch.lengths)
    probabilities = softmax_with_temperature(logits, temperature=temperature)
    bounded_top_k = min(max(top_k, 1), probabilities.shape[-1])
    topk_probabilities, topk_indices = torch.topk(probabilities, k=bounded_top_k, dim=-1)
    topk_mmsi = [
        [class_to_mmsi[int(index)] for index in row.tolist()]
        for row in topk_indices.cpu()
    ]
    assignment = soft_assign_boats(
        logits,
        temperature=temperature,
        top_k=top_k,
        confidence_threshold=confidence_threshold,
    )
    return TopKMmsiPredictions(
        logits=logits,
        probabilities=probabilities,
        topk_indices=topk_indices,
        topk_mmsi=topk_mmsi,
        topk_probabilities=topk_probabilities,
        assignment=assignment,
    )
