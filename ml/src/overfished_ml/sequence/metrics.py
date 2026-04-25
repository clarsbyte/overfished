"""Metrics and ensembling helpers for sequence classifiers."""

from __future__ import annotations

import torch
from torch import Tensor


def topk_accuracy(logits: Tensor, targets: Tensor, k: int = 1) -> float:
    """Compute top-k accuracy."""
    if logits.numel() == 0:
        return 0.0
    topk = torch.topk(logits, k=min(k, logits.shape[1]), dim=1).indices
    matches = (topk == targets.unsqueeze(1)).any(dim=1)
    return float(matches.float().mean().item())


def brier_score(probabilities: Tensor, targets: Tensor) -> float:
    """Compute multi-class Brier score."""
    one_hot = torch.zeros_like(probabilities)
    one_hot.scatter_(1, targets.unsqueeze(1), 1.0)
    return float(torch.mean((probabilities - one_hot) ** 2).item())


def expected_calibration_error(
    probabilities: Tensor,
    targets: Tensor,
    *,
    n_bins: int = 10,
) -> float:
    """Compute ECE from confidence bins."""
    confidences, predictions = probabilities.max(dim=1)
    accuracies = predictions.eq(targets)

    ece = torch.tensor(0.0, dtype=probabilities.dtype, device=probabilities.device)
    bin_edges = torch.linspace(0, 1, n_bins + 1, device=probabilities.device)
    for bin_start, bin_end in zip(bin_edges[:-1], bin_edges[1:]):
        in_bin = (confidences > bin_start) & (confidences <= bin_end)
        if in_bin.any():
            prop = in_bin.float().mean()
            accuracy = accuracies[in_bin].float().mean()
            confidence = confidences[in_bin].mean()
            ece += torch.abs(confidence - accuracy) * prop
    return float(ece.item())


def classification_metrics(logits: Tensor, targets: Tensor, *, top_k: int = 3) -> dict[str, float]:
    """Compute core sequence classification metrics."""
    probabilities = torch.softmax(logits, dim=1)
    return {
        "top1_accuracy": topk_accuracy(logits, targets, k=1),
        "topk_accuracy": topk_accuracy(logits, targets, k=top_k),
        "brier_score": brier_score(probabilities, targets),
        "ece": expected_calibration_error(probabilities, targets),
    }


def ensemble_probabilities(probability_tensors: list[Tensor]) -> Tensor:
    """Average a set of probability tensors and renormalize."""
    if not probability_tensors:
        raise ValueError("probability_tensors cannot be empty")
    stacked = torch.stack(probability_tensors, dim=0)
    averaged = stacked.mean(dim=0)
    normalizer = averaged.sum(dim=1, keepdim=True).clamp(min=1e-12)
    return averaged / normalizer
