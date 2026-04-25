"""Pipeline helpers for sequence model scoring and assignment."""

from __future__ import annotations

from dataclasses import dataclass

from torch import Tensor, nn

from .assignment import AssignmentResult, apply_confidence_threshold, softmax_with_temperature, topk_renormalize


@dataclass(frozen=True)
class SequenceBatch:
    """Batched padded sequence features."""

    features: Tensor
    lengths: Tensor


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
