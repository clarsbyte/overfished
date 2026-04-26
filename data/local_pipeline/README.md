# Local Pipeline Data

- `build_river_plastic_geojson.py` — one-shot: Meijer et al. 2021 (figshare) shapefile → slim `frontend/public/data/river_plastic_emissions.geojson` (requires `pip install geopandas`). The repo ships a small illustrative GeoJSON so Mapbox can load the layer without the download; replace the file with script output for the full outfall set.
- `sample_fishing_events.csv`: committed sample input for reproducible local runs.
- `sample_ship_detections.csv`: committed sample ship detections subset.
- `raw/`: place full-size raw extracts here (see [`raw/README.md`](raw/README.md)); `raw/bulk_fishing_events.csv` is used automatically if present, or set `FISHING_EVENTS_CSV` to a repo-relative path.
- `output/`: generated medallion outputs (gitignored).
- `ship_image_overrides.example.csv`: template for manual MMSI → image URL rows (copy to `ship_image_overrides.csv`).
- `ship_image_overrides.csv`: optional curated URLs (not committed by default; same folder).
- `vessel_image_cache.json` / `vessel_image_misses.json`: enrichment run artifacts.
- For demos without API calls: run `overfished-enrich-images --offline` (uses cache + CSV URLs + overrides only).

## GX10 (ASUS Ascent) and heavy runs

Set `GX10_HOST`, `GX10_USER`, `GX10_REMOTE_WORKDIR` (and optional `GX10_SSH_KEY_PATH`, `GX10_SSH_PORT`).

- **Sync + Spark on the remote** (rsyncs `ml/` and full `data/` by default, then runs PySpark in `GX10_REMOTE_WORKDIR` as the repo root):

  ```bash
  overfished-pipeline --runtime gx10 --sync-gx10
  ```

  With large CSV, tune Spark (locally; flags are passed through SSH):

  ```bash
  export SPARK_SHUFFLE_PARTITIONS=200 SPARK_DRIVER_MEMORY=16g
  overfished-pipeline --runtime gx10 --sync-gx10 --input-path data/local_pipeline/raw/bulk_fishing_events.csv
  ```

  `SPARK_SHUFFLE_PARTITIONS`, `SPARK_DRIVER_MEMORY`, `SPARK_MASTER`, etc. are read from the environment; CLI `--spark-*` overrides. Use `--gx10-minimal-data-sync` to only sync `data/local_pipeline/`.

- **Image URL enrichment on GX10** (headless, fast network; not Spark):

  ```bash
  overfished-gx10 sync
  overfished-gx10 enrich
  overfished-gx10 pull
  ```

  `pull` rsyncs `data/local_pipeline/output/`, image caches, and `data/gold_vessel_detections_enriched.csv` from the host.

- Optional: `GX10_SYNC_EXTRA=path/to/extra` comma-separated repo-relative paths for one-off rsync after the main sync.
