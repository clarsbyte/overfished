# Databricks (Overfished)

This folder holds a **Databricks Asset Bundle** scaffold for jobs, notebooks, and MLflow/Unity Catalog workflows—**not** the Next.js runtime.

## Ownership (edit names)

| Asset type | Responsible (R) | Accountable (A) |
|------------|------------------|------------------|
| Workspace sync / bundle deploy | TBD | TBD |
| CV training job (e.g. SAR / YOLO) | TBD | TBD |
| Cached API / feature tables | TBD | TBD |
| MLflow experiments & model registry | TBD | TBD |

## Next steps

1. Replace `workspace.host` in [databricks.yml](databricks.yml) with your workspace URL (or use bundle variables / profiles per Databricks docs).
2. Add job definitions under `resources/` pointing at notebooks in this repo or in the workspace.
3. Align training/inference contracts with [../ml/README.md](../ml/README.md).

## CLI

```bash
databricks bundle validate
databricks bundle deploy --target dev
```

Authenticate with `DATABRICKS_HOST` and `DATABRICKS_TOKEN` (or `databricks auth`), never commit tokens.
