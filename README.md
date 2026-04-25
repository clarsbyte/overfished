# Overfished

Surface illegal or high-risk fishing using vessel activity, regional regulations, and evidence-style artifacts suitable for enforcement demos (LA Hacks / hackathon scope).

## User journey (high level)

1. Draw or select a region on the map.
2. Inspect activity and heatmap-style signals (fused from external fishing-data APIs).
3. Optionally highlight SAR / computer-vision detections as a **showcase** narrative.
4. Produce narrative and artifacts (reports, simulated hail, etc.) via the API, optionally backed by an agent plugin.

## Honesty and scope

- External fishing APIs are **near-real-time**, not live; product copy should say so.
- Operational vessel detections may come from provider-classified data; custom CV (e.g. SAR / YOLO) is a **separate showcase path** documented in [ml/](ml/) and optionally [databricks/](databricks/README.md).

## Stack and layers

| Layer | Location | Role |
|-------|----------|------|
| Presentation | [frontend/](frontend/) | Vite + React; proxies `/api` and `/agentapi` in dev (see `frontend/vite.config.ts`). |
| API (BFF) | [api/](api/) | FastAPI agents + sequence + `POST /comms/call` (default local port **8001**). |
| Demo REST | [backend/api/](backend/api/) | Vessels, heatmap, species, Twilio AI-call webhooks (default **8000**). |
| ML library | [ml/](ml/) | Local-first medallion ETL + sequence/CV modules; can run without Databricks. |
| Agent plugins (optional) | [plugins/langchain_plugin/](plugins/langchain_plugin/), [plugins/fetch_plugin/](plugins/fetch_plugin/) | LangChain and/or Fetch-style orchestration behind `AgentBackend`. |
| Databricks (optional) | [databricks/](databricks/) | Jobs, notebooks, MLflow / Unity Catalog when cloud orchestration is needed. |

Architecture detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Repository layout

```text
frontend/                 Vite + React app
api/                      FastAPI BFF (routers + ports + deps)
backend/api/              Demo REST API for map + fixtures
ml/                       Local-first ML package (pipeline + sequence/CV modules)
plugins/langchain_plugin/ Optional LangChain implementation of AgentBackend
plugins/fetch_plugin/     Optional Fetch.ai-style implementation of AgentBackend
databricks/               Asset bundle placeholder + platform README
docs/                     Architecture notes
```

## Environment variables (names only)

Set these in deployment or `.env` for the API (see [api/](api/) when running locally). Do not commit secrets.

| Name | Used by | Purpose |
|------|---------|---------|
| `AGENT_BACKEND` | API | `noop` (default), `langchain`, `fetch`, or `hybrid` (`fetch_hybrid`). |
| `FETCH_AGENT_ENABLED` | API hybrid/fetch | Toggle Fetch path in hybrid mode (`true`/`false`). |
| `FETCH_AGENT_TIMEOUT_SECONDS` | API hybrid/fetch | Timeout budget for Fetch attempt before fallback. |
| `FETCH_AGENT_MAX_RETRIES` | API hybrid/fetch | Bounded retry attempts before fallback. |
| `VITE_API_URL` | Frontend | Demo REST base (empty = `/api` Vite proxy → :8000). |
| `VITE_AGENT_API_URL` | Frontend | BFF base (empty = `/agentapi` proxy → :8001). |
| `MAP_BOX_TOKEN` | Frontend | Mapbox GL token (repo-root `.env` with Vite `envDir`, or `frontend/.env`). |
| `SKIP_DATA_LINK` | Frontend `predev` / `prebuild` | Set `1` to skip `public/data` symlink when `data/local_pipeline` is missing (e.g. CI). |
| `DATABRICKS_HOST` | Databricks CLI / jobs | Workspace host. |
| `DATABRICKS_TOKEN` | Databricks CLI / jobs | PAT (never commit). |
| `MLFLOW_TRACKING_URI` | ML jobs (optional) | Experiment tracking. |
| `GX10_HOST` | ML pipeline runtime | Remote host/IP for optional GX10 SSH execution. |
| `GX10_USER` | ML pipeline runtime | SSH user for GX10 execution. |
| `GX10_REMOTE_WORKDIR` | ML pipeline runtime | Remote directory where synced code/data are executed. |
| `GX10_SSH_KEY_PATH` | ML pipeline runtime (optional) | SSH private key path for GX10 auth. |
| `GX10_SSH_PORT` | ML pipeline runtime (optional) | SSH port (default `22`). |
| `VESSEL_IMAGE_OFFLINE` | ML image enrichment (optional) | Set `1` to use only cache/CSV/overrides (no MarineTraffic or Commons). |

## Install and run (scaffold)

**Frontend** (expects both backends below if you use agents + map data APIs)

```bash
cd frontend && npm install && npm run dev
```

`predev` runs `link-data.mjs` (symlink `public/data` → `data/local_pipeline`) and TypeScript codegen from `backend/tools/schemas.py`. Use `SKIP_DATA_LINK=1` when that folder is absent.

**Demo REST API** (vessels, heatmap, species, Twilio case flows)

```bash
cd backend && pip install -r requirements.txt
USE_FIXTURES=1 uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

**BFF** (LangChain agents, sequence routes, `POST /comms/call`)

```bash
cd api && pip install -e ".[dev]"
uvicorn overfished_api.main:app --reload --host 0.0.0.0 --port 8001
```

See [api/README.md](api/README.md) for env vars and endpoint tables.

**Optional LangChain plugin**

From the repository root (so both editables share the same environment):

```bash
pip install -e ./api
pip install -e "./plugins/langchain_plugin[langchain]"
export AGENT_BACKEND=langchain
```

The plugin does not declare a path dependency on `overfished-api`; install the API package first.

With `AGENT_BACKEND=noop` (default), LangChain is not required.

**Optional Fetch plugin (standalone or hybrid)**

```bash
pip install -e ./api
pip install -e ./plugins/fetch_plugin
export AGENT_BACKEND=fetch      # or hybrid
```

For hackathon stability, `AGENT_BACKEND=hybrid` routes `/agent/run` through Fetch first and
falls back deterministically if Fetch times out/errors.

**Medallion Spark on ASUS GX10 and bulk fishing events**

- Put large GFW/warehouse-style CSVs under `data/local_pipeline/raw/` (see [data/local_pipeline/raw/README.md](data/local_pipeline/raw/README.md)) or set `FISHING_EVENTS_CSV` to a repo-relative path.
- On a GX10 with `GX10_HOST` / `GX10_USER` / `GX10_REMOTE_WORKDIR` set: `overfished-pipeline --runtime gx10 --sync-gx10` (tune with `SPARK_SHUFFLE_PARTITIONS`, `SPARK_DRIVER_MEMORY`, etc.).
- For headless **image URL** enrichment on GX10: `overfished-gx10 sync && overfished-gx10 enrich && overfished-gx10 pull` (see [ml/README.md](ml/README.md) and [data/local_pipeline/README.md](data/local_pipeline/README.md)).

**Sequence model (RNN + BiLSTM) and “sus” ships (optional)**

Install the ML package into the **same** venv as the BFF, then restart the BFF on **8001**:

```bash
# from repo root, with .venv active
pip install -e "./ml[dev]"   # torch + overfished_ml; see [ml/README.md](ml/)
```

- **HTTP demo (browser or curl, ~10–20s first time):**  
  [http://127.0.0.1:8001/ml/sequence/demo](http://127.0.0.1:8001/ml/sequence/demo)  
  Returns JSON with soft per-class scores, a short `narration`, and a `suspect_readout` of MMSI windows where the ensemble is uncertain or disagrees with the label (triage / demo only).

- **Agent (`fetch` / `hybrid`):** ask for suspicious / sus vessels or the sequence model; the Fetch plugin runs the same report. Example body for `POST /agent/run`:

```json
{
  "query": "Which ships are sus based on the sequence model?",
  "context": { "use_synthetic": true, "epochs": 1 }
}
```

or another I like to use :

```
curl -sS http://127.0.0.1:8000/agent/run \
  -H "Content-Type: application/json" \
  -d '{"query":"Which ships are sus based on the sequence model?","context":{"use_synthetic":true,"epochs":1}}'
```

(Queries that mention e.g. `sus`, `suspicious`, `BILSTM`, `LSTM`, or `sequence: true` in `context` route to this path. Use repo CSV via `context.csv_path` like `data/local_pipeline/sample_fishing_events.csv` when you are not using synthetic data.)

## Who does what (RACI)

Replace **TBD** with teammate names. **R** = Responsible, **A** = Accountable, **C** = Consulted, **I** = Informed.

| Area | R | A | C | I |
|------|---|---|---|---|
| Map UI, heatmap, demo UX | TBD | TBD | API owner | Whole team |
| BFF API, routing, caching strategy, OpenAPI | TBD | TBD | Databricks (data contracts) | Frontend |
| External API clients (e.g. GFW), rate limits | TBD | TBD | Legal / ToS | Agent owner |
| Databricks jobs, tables, MLflow | TBD | TBD | CV owner | API |
| CV pipeline (e.g. SAR / YOLO showcase) | TBD | TBD | Databricks admin | Demo lead |
| LangChain plugin (tools, prompts, wiring) | TBD | TBD | API (`ports/`) | Frontend (copy/UX) |
| Demo script, pre-cached JSON, stage narrative | TBD | TBD | All signal owners | Judges |

## Definition of done (per layer, for this scaffold)

- **Frontend**: App runs; `NEXT_PUBLIC_API_BASE_URL` documented; domain calls go through the BFF only.
- **API**: `/health` returns OK; OpenAPI served at `/docs`; `AgentBackend` bound via `deps` (`noop` default).
- **ML**: Importable package; CV modules are documented stubs with no training implementation.
- **Plugin**: Optional install; `build_agent_backend()` returns an object satisfying `AgentBackend` (stub responses only).
- **Databricks**: Bundle validates or documents next steps; README names job/notebook ownership.

## Operations (external APIs)

Long-running or rate-limited upstream APIs (e.g. concurrent limits, gateway timeouts on heavy reports) make **pre-cached JSON** and a **live vs demo** toggle the default posture for demos. See internal planning docs; implement caching in the API layer when you add real clients.

## License

TBD.
