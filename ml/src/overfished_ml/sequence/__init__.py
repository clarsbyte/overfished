"""Sequence modeling utilities for vessel/boat assignment."""

from .assignment import (
    AssignmentResult,
    apply_confidence_threshold,
    softmax_with_temperature,
    topk_renormalize,
)
from .data_loader import DatabricksConnectionConfig, load_golden_dataset
from .dataset import (
    MmsiSequenceDataset,
    SequenceDatasetBundle,
    SequenceExample,
    SequenceTrainingBatch,
    build_mmsi_class_map,
    collate_sequence_batch,
    prepare_sequence_datasets,
)
from .metrics import classification_metrics, ensemble_probabilities
from .models import BoatBiLSTMClassifier, BoatRNNClassifier, build_model
from .pipeline import SequenceBatch, TopKMmsiPredictions, forward_scores, predict_topk_mmsi, soft_assign_boats
from .report import (
    build_sequence_report,
    format_sequence_narration,
    normalize_fishing_dataframe,
    resolve_allowed_csv_path,
    synthetic_events_dataframe,
)
from .train import ModelTrainingResult, TrainingComparisonResult, TrainingConfig, train_and_compare_models, train_sequence_model

__all__ = [
    "AssignmentResult",
    "BoatBiLSTMClassifier",
    "BoatRNNClassifier",
    "DatabricksConnectionConfig",
    "ModelTrainingResult",
    "build_sequence_report",
    "format_sequence_narration",
    "normalize_fishing_dataframe",
    "resolve_allowed_csv_path",
    "synthetic_events_dataframe",
    "MmsiSequenceDataset",
    "SequenceBatch",
    "SequenceDatasetBundle",
    "SequenceExample",
    "SequenceTrainingBatch",
    "TopKMmsiPredictions",
    "TrainingComparisonResult",
    "TrainingConfig",
    "apply_confidence_threshold",
    "build_mmsi_class_map",
    "build_model",
    "classification_metrics",
    "collate_sequence_batch",
    "ensemble_probabilities",
    "forward_scores",
    "load_golden_dataset",
    "predict_topk_mmsi",
    "prepare_sequence_datasets",
    "soft_assign_boats",
    "softmax_with_temperature",
    "train_and_compare_models",
    "train_sequence_model",
    "topk_renormalize",
]
