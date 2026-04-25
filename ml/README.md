# overfished-ml

Package for local-first overfishing ML workflows. Databricks remains optional for
warehouse-backed training, while the medallion ETL pipeline now runs fully local
by default.

This repository currently includes:

- local medallion ETL in `overfished_ml.local_pipeline` (bronze/silver/gold)
- CV train/infer entrypoint stubs in `overfished_ml.cv`
- sequence-model scaffolding in `overfished_ml.sequence`:
  - `BoatRNNClassifier`
  - `BoatBiLSTMClassifier`
  - soft assignment helpers for boat allocation probabilities

See [../README.md](../README.md) and [../databricks/README.md](../databricks/README.md).

## Local Medallion Pipeline (Default)

### Install

From `ml/`:

```bash
pip install -e ".[dev]"
```

### Run locally

From `ml/`:

```bash
overfished-pipeline --runtime local
```

You can also run with `python -m overfished_ml.local_pipeline.cli --runtime local`.
Requires Java 17+ for Spark runtime compatibility.

Default committed input:
- `../data/local_pipeline/sample_fishing_events.csv`

Default outputs:
- `../data/local_pipeline/output/bronze_fishing_events`
- `../data/local_pipeline/output/silver_fishing_events`
- `../data/local_pipeline/output/gold_fishing_features`
- `../data/local_pipeline/output/gold_fishing_features_csv`

### Run on ASUS Ascent GX10 (optional over SSH)

Set:

```bash
export GX10_HOST=<host-or-ip>
export GX10_USER=<ssh-user>
export GX10_REMOTE_WORKDIR=<remote-dir>
export GX10_SSH_PORT=22              # optional
export GX10_SSH_KEY_PATH=~/.ssh/id_rsa  # optional
```

Then run:

```bash
overfished-pipeline --runtime gx10 --sync-gx10
```

This syncs `ml/` and `data/local_pipeline/` to the remote workdir and executes
the same pipeline command on GX10.

### Data policy

- Commit only sample inputs in `../data/local_pipeline/`.
- Put full raw extracts in `../data/local_pipeline/raw/` (ignored by git).
- Generated outputs in `../data/local_pipeline/output/` are ignored by git.

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
