"""PyTorch sequence classifiers for boat prediction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import torch
from torch import Tensor, nn

ModelType = Literal["rnn", "bilstm"]


def _masked_mean_pool(sequence_outputs: Tensor, lengths: Tensor) -> Tensor:
    """Average non-padded timestep embeddings for each sequence."""
    batch_size, max_steps, _ = sequence_outputs.shape
    device = sequence_outputs.device
    steps = torch.arange(max_steps, device=device).unsqueeze(0).expand(batch_size, max_steps)
    mask = (steps < lengths.unsqueeze(1)).unsqueeze(2)
    masked = sequence_outputs * mask
    denominator = lengths.clamp(min=1).unsqueeze(1).to(sequence_outputs.dtype)
    return masked.sum(dim=1) / denominator


@dataclass(frozen=True)
class SequenceModelConfig:
    """Configuration for sequence classifiers."""

    input_dim: int
    hidden_dim: int
    num_classes: int
    num_layers: int = 1
    dropout: float = 0.0


class BoatRNNClassifier(nn.Module):
    """Vanilla RNN classifier over padded feature sequences."""

    def __init__(self, config: SequenceModelConfig) -> None:
        super().__init__()
        self.config = config
        self.rnn = nn.RNN(
            input_size=config.input_dim,
            hidden_size=config.hidden_dim,
            num_layers=config.num_layers,
            batch_first=True,
            dropout=config.dropout if config.num_layers > 1 else 0.0,
        )
        self.classifier = nn.Linear(config.hidden_dim, config.num_classes)

    def forward(self, features: Tensor, lengths: Tensor) -> Tensor:
        packed = nn.utils.rnn.pack_padded_sequence(
            features, lengths.cpu(), batch_first=True, enforce_sorted=False
        )
        packed_out, _ = self.rnn(packed)
        unpacked, _ = nn.utils.rnn.pad_packed_sequence(packed_out, batch_first=True)
        pooled = _masked_mean_pool(unpacked, lengths)
        return self.classifier(pooled)


class BoatBiLSTMClassifier(nn.Module):
    """Bidirectional LSTM classifier over padded feature sequences."""

    def __init__(self, config: SequenceModelConfig) -> None:
        super().__init__()
        self.config = config
        self.lstm = nn.LSTM(
            input_size=config.input_dim,
            hidden_size=config.hidden_dim,
            num_layers=config.num_layers,
            batch_first=True,
            dropout=config.dropout if config.num_layers > 1 else 0.0,
            bidirectional=True,
        )
        self.classifier = nn.Linear(config.hidden_dim * 2, config.num_classes)

    def forward(self, features: Tensor, lengths: Tensor) -> Tensor:
        packed = nn.utils.rnn.pack_padded_sequence(
            features, lengths.cpu(), batch_first=True, enforce_sorted=False
        )
        packed_out, _ = self.lstm(packed)
        unpacked, _ = nn.utils.rnn.pad_packed_sequence(packed_out, batch_first=True)
        pooled = _masked_mean_pool(unpacked, lengths)
        return self.classifier(pooled)


def build_model(model_type: ModelType, config: SequenceModelConfig) -> nn.Module:
    """Factory for sequence classifier selection."""
    if model_type == "rnn":
        return BoatRNNClassifier(config)
    if model_type == "bilstm":
        return BoatBiLSTMClassifier(config)
    raise ValueError(f"Unsupported model_type: {model_type}")
