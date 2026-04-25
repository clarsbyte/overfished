"""Dataset preparation utilities for MMSI sequence training."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd
import torch
from torch import Tensor
from torch.nn.utils.rnn import pad_sequence
from torch.utils.data import Dataset

REQUIRED_COLUMNS = ("mmsi", "event_start")
EXCLUDED_FEATURE_COLUMNS = {
    "mmsi",
    "vessel_id",
    "vessel_name",
    "image_id",
    "event_id",
    "event_start",
    "event_end",
    "image_timestamp",
    "ingested_at",
    "fishing_processed_at",
    "detection_processed_at",
}


@dataclass(frozen=True)
class SequenceExample:
    """A single vessel sequence sample and target class."""

    features: Tensor
    target_class: int
    mmsi: str


@dataclass(frozen=True)
class SequenceTrainingBatch:
    """Padded batch used during model training/evaluation."""

    features: Tensor
    lengths: Tensor
    targets: Tensor


@dataclass(frozen=True)
class SequenceDatasetBundle:
    """Prepared datasets and metadata for sequence training."""

    train_dataset: "MmsiSequenceDataset"
    val_dataset: "MmsiSequenceDataset"
    mmsi_to_class: dict[str, int]
    class_to_mmsi: dict[int, str]
    feature_columns: list[str]
    input_dim: int


class MmsiSequenceDataset(Dataset[SequenceExample]):
    """Torch dataset of variable-length MMSI sequence examples."""

    def __init__(self, examples: list[SequenceExample]) -> None:
        self.examples = examples

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> SequenceExample:
        return self.examples[index]


def build_mmsi_class_map(dataframe: pd.DataFrame) -> tuple[dict[str, int], dict[int, str]]:
    """Build deterministic MMSI <-> class-id maps."""
    if "mmsi" not in dataframe.columns:
        raise ValueError("dataframe must include `mmsi` column")
    mmsi_values = sorted(str(value) for value in dataframe["mmsi"].dropna().unique())
    mmsi_to_class = {mmsi: idx for idx, mmsi in enumerate(mmsi_values)}
    class_to_mmsi = {idx: mmsi for mmsi, idx in mmsi_to_class.items()}
    return mmsi_to_class, class_to_mmsi


def prepare_sequence_datasets(
    dataframe: pd.DataFrame,
    *,
    seq_len: int = 8,
    stride: int = 1,
    val_fraction: float = 0.2,
    feature_columns: list[str] | None = None,
) -> SequenceDatasetBundle:
    """Create train/validation sequence datasets grouped by MMSI."""
    if seq_len <= 0:
        raise ValueError("seq_len must be > 0")
    if stride <= 0:
        raise ValueError("stride must be > 0")
    if not 0.0 <= val_fraction < 1.0:
        raise ValueError("val_fraction must be in [0.0, 1.0)")

    _validate_required_columns(dataframe, REQUIRED_COLUMNS)
    working = dataframe.copy()
    working["mmsi"] = working["mmsi"].astype(str)
    working["event_start"] = pd.to_datetime(working["event_start"], errors="coerce", utc=True)
    working = working.dropna(subset=["mmsi", "event_start"])
    if working.empty:
        raise ValueError("No usable rows after parsing `mmsi` and `event_start`")

    working = _expand_categorical_features(working)
    selected_feature_columns = feature_columns or infer_feature_columns(working)
    if not selected_feature_columns:
        raise ValueError("Could not infer feature columns; provide `feature_columns` explicitly")

    feature_frame = working[selected_feature_columns].apply(pd.to_numeric, errors="coerce")
    feature_frame = feature_frame.fillna(feature_frame.median(numeric_only=True)).fillna(0.0)
    working[selected_feature_columns] = _zscore(feature_frame)
    working = working.sort_values(["mmsi", "event_start"]).reset_index(drop=True)

    mmsi_to_class, class_to_mmsi = build_mmsi_class_map(working)
    train_examples, val_examples = _build_windowed_examples(
        working,
        mmsi_to_class=mmsi_to_class,
        feature_columns=selected_feature_columns,
        seq_len=seq_len,
        stride=stride,
        val_fraction=val_fraction,
    )

    if not train_examples:
        raise ValueError("No training windows were created. Check seq_len/stride and source data.")

    return SequenceDatasetBundle(
        train_dataset=MmsiSequenceDataset(train_examples),
        val_dataset=MmsiSequenceDataset(val_examples),
        mmsi_to_class=mmsi_to_class,
        class_to_mmsi=class_to_mmsi,
        feature_columns=selected_feature_columns,
        input_dim=len(selected_feature_columns),
    )


def infer_feature_columns(dataframe: pd.DataFrame) -> list[str]:
    """Infer numeric feature columns after one-hot expansion."""
    numeric_columns = dataframe.select_dtypes(include=["number", "bool"]).columns.tolist()
    return [column for column in numeric_columns if column not in EXCLUDED_FEATURE_COLUMNS]


def collate_sequence_batch(examples: list[SequenceExample]) -> SequenceTrainingBatch:
    """Pad sequence batch and return tensors with lengths and targets."""
    sorted_examples = sorted(examples, key=lambda example: example.features.shape[0], reverse=True)
    sequence_tensors = [example.features for example in sorted_examples]
    lengths = torch.tensor([tensor.shape[0] for tensor in sequence_tensors], dtype=torch.long)
    padded_features = pad_sequence(sequence_tensors, batch_first=True)
    targets = torch.tensor([example.target_class for example in sorted_examples], dtype=torch.long)
    return SequenceTrainingBatch(features=padded_features, lengths=lengths, targets=targets)


def _validate_required_columns(dataframe: pd.DataFrame, required_columns: Iterable[str]) -> None:
    missing = sorted(column for column in required_columns if column not in dataframe.columns)
    if missing:
        raise ValueError(f"Dataframe is missing required columns: {missing}")


def _expand_categorical_features(dataframe: pd.DataFrame) -> pd.DataFrame:
    categorical_columns = [
        column
        for column in ("vessel_type", "vessel_flag", "event_type", "detection_source")
        if column in dataframe.columns
    ]
    if not categorical_columns:
        return dataframe
    return pd.get_dummies(dataframe, columns=categorical_columns, dummy_na=True)


def _zscore(feature_frame: pd.DataFrame) -> pd.DataFrame:
    means = feature_frame.mean()
    stds = feature_frame.std(ddof=0).replace(0, 1.0)
    return (feature_frame - means) / stds


def _build_windowed_examples(
    dataframe: pd.DataFrame,
    *,
    mmsi_to_class: dict[str, int],
    feature_columns: list[str],
    seq_len: int,
    stride: int,
    val_fraction: float,
) -> tuple[list[SequenceExample], list[SequenceExample]]:
    train_examples: list[SequenceExample] = []
    val_examples: list[SequenceExample] = []

    for mmsi, vessel_rows in dataframe.groupby("mmsi", sort=False):
        matrix = vessel_rows[feature_columns].to_numpy(dtype="float32")
        windows = []
        for start_idx in range(0, len(matrix), stride):
            end_idx = min(start_idx + seq_len, len(matrix))
            window = matrix[start_idx:end_idx]
            if len(window) == 0:
                continue
            windows.append(
                SequenceExample(
                    features=torch.tensor(window, dtype=torch.float32),
                    target_class=mmsi_to_class[mmsi],
                    mmsi=mmsi,
                )
            )

        if not windows:
            continue
        val_count = int(len(windows) * val_fraction)
        if val_fraction > 0.0 and len(windows) > 1:
            val_count = max(1, val_count)
        split_idx = len(windows) - val_count
        train_examples.extend(windows[:split_idx] if split_idx > 0 else windows)
        if split_idx > 0:
            val_examples.extend(windows[split_idx:])

    return train_examples, val_examples
