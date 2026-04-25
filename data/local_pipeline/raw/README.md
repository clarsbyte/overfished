# Bulk fishing events (large CSV)

Place a **GFW- or warehouse-style** export here for the medallion pipeline. It must match the same general column layout as [`../sample_fishing_events.csv`](../sample_fishing_events.csv) (see [`transformations.py`](../../../ml/src/overfished_ml/local_pipeline/transformations.py) for expected fields).

**Default path:** `bulk_fishing_events.csv` in this directory.

If that file exists, `PipelinePaths.default()` uses it automatically (unless `FISHING_EVENTS_CSV` is set). You can also set:

```bash
export FISHING_EVENTS_CSV=data/local_pipeline/raw/my_export.csv
overfished-pipeline --runtime local
```

Large files are gitignored by pattern; keep them on disk or object storage and document the source per run.
