# overfished-ml

Package for computer-vision and sequence-model workflows intended to run primarily
on **Databricks** (notebooks, jobs, MLflow, Unity Catalog).

This repository currently includes:

- CV train/infer entrypoint stubs in `overfished_ml.cv`
- sequence-model scaffolding in `overfished_ml.sequence`:
  - `BoatRNNClassifier`
  - `BoatBiLSTMClassifier`
  - soft assignment helpers for boat allocation probabilities

See [../README.md](../README.md) and [../databricks/README.md](../databricks/README.md).

## Sequence module quickstart

```python
import torch

from overfished_ml.sequence import (
    SequenceBatch,
    build_model,
    forward_scores,
    soft_assign_boats,
)
from overfished_ml.sequence.models import SequenceModelConfig

config = SequenceModelConfig(input_dim=16, hidden_dim=32, num_classes=5)
model = build_model("bilstm", config)

features = torch.randn(4, 12, 16)  # batch, steps, feature_dim
lengths = torch.tensor([12, 10, 9, 7], dtype=torch.long)
batch = SequenceBatch(features=features, lengths=lengths)

logits, _ = forward_scores(model, batch)
assignment = soft_assign_boats(logits, temperature=0.8, top_k=3, confidence_threshold=0.4)
```

## Golden dataset loader (Databricks SQL)

Use one shared loader so the RNN, BiLSTM, and assignment workflows start from
the same validated DataFrame.

Required environment variables:

- `DATABRICKS_HOST`
- `DATABRICKS_TOKEN`
- `DATABRICKS_WAREHOUSE_ID`
- optional `DATABRICKS_GOLD_TABLE` (defaults to `workspace.default.gold_vessel_detections_enriched`)

Never commit `.env` files with real tokens.

```python
from overfished_ml.sequence import DatabricksConnectionConfig, load_golden_dataset

config = DatabricksConnectionConfig.from_env()
required_columns = ["mmsi", "event_ts", "lat", "lon"]
gold_df = load_golden_dataset(config, required_columns=required_columns)
```

## Train predictive RNN + 1D-BiLSTM

The sequence training pipeline groups rows by `mmsi`, sorts by `event_start`,
and trains both RNN and BiLSTM models to output global MMSI soft-assignment
probabilities.

```python
from pathlib import Path

import pandas as pd
from overfished_ml.sequence import (
    DatabricksConnectionConfig,
    TrainingConfig,
    load_golden_dataset,
    train_and_compare_models,
)

config = DatabricksConnectionConfig.from_env()
gold_df = load_golden_dataset(config, required_columns=["mmsi", "event_start"])

training_config = TrainingConfig(
    seq_len=8,
    stride=1,
    val_fraction=0.2,
    batch_size=16,
    epochs=10,
    hidden_dim=64,
    checkpoint_dir=str(Path("artifacts/checkpoints")),
)
comparison = train_and_compare_models(gold_df, config=training_config)

print("Selected model:", comparison.selected_model_type)
print("RNN metrics:", comparison.rnn_result.metrics)
print("BiLSTM metrics:", comparison.bilstm_result.metrics)
print("Ensemble metrics:", comparison.ensemble_metrics)
```

For local/offline iteration, replace the loader call with:

```python
gold_df = pd.read_csv("../data/gold_vessel_detections_enriched.csv")
```
