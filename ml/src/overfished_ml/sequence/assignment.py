"""Soft boat-assignment utilities."""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import Tensor


@dataclass(frozen=True)
class AssignmentResult:
    """Assignment outputs for each sequence sample."""

    probabilities: Tensor
    assigned_index: Tensor
    assigned_confidence: Tensor
    is_unassigned: Tensor


def softmax_with_temperature(logits: Tensor, temperature: float = 1.0) -> Tensor:
    """Compute a temperature-scaled softmax over logits."""
    if temperature <= 0.0:
        raise ValueError("temperature must be > 0")
    return torch.softmax(logits / temperature, dim=-1)


def topk_renormalize(probabilities: Tensor, top_k: int | None = None) -> Tensor:
    """Keep top-k probabilities per row and renormalize."""
    if top_k is None:
        return probabilities
    if top_k <= 0:
        raise ValueError("top_k must be > 0 when provided")
    if top_k >= probabilities.shape[-1]:
        return probabilities

    values, indices = torch.topk(probabilities, k=top_k, dim=-1)
    filtered = torch.zeros_like(probabilities)
    filtered.scatter_(dim=-1, index=indices, src=values)
    normalizer = filtered.sum(dim=-1, keepdim=True).clamp(min=1e-12)
    return filtered / normalizer


def apply_confidence_threshold(
    probabilities: Tensor, confidence_threshold: float | None = None
) -> AssignmentResult:
    """Convert soft probabilities into best assignment with optional abstain flag."""
    if confidence_threshold is not None and not 0.0 <= confidence_threshold <= 1.0:
        raise ValueError("confidence_threshold must be between 0 and 1")

    assigned_confidence, assigned_index = torch.max(probabilities, dim=-1)
    if confidence_threshold is None:
        is_unassigned = torch.zeros_like(assigned_confidence, dtype=torch.bool)
    else:
        is_unassigned = assigned_confidence < confidence_threshold

    return AssignmentResult(
        probabilities=probabilities,
        assigned_index=assigned_index,
        assigned_confidence=assigned_confidence,
        is_unassigned=is_unassigned,
    )
