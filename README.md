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
| Presentation | [frontend/](frontend/) | Vite + React; calls the BFF over HTTP only. |
| API (BFF) | [api/](api/) | FastAPI routes, OpenAPI, DI; **no** embedded business logic in this scaffold. |
| ML library | [ml/](ml/) | Local-first medallion ETL + sequence/CV modules; can run without Databricks. |
| Agent plugins (optional) | [plugins/langchain_plugin/](plugins/langchain_plugin/), [plugins/fetch_plugin/](plugins/fetch_plugin/) | LangChain and/or Fetch-style orchestration behind `AgentBackend`. |
| Databricks (optional) | [databricks/](databricks/) | Jobs, notebooks, MLflow / Unity Catalog when cloud orchestration is needed. |

Architecture detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## startup (full stack, local)

**startup** = bring up Python/ML/proxy *prep* (if needed) plus the map/demo API, the auth + agent + sequence BFF, and the Vite app with linked data (as on `npm run dev`). In Cursor, when you say *startup*, the agent should use this flow.

```bash
./scripts/startup.sh
```

`startup.sh` runs, in order (unless you skip; see below):

1. **Python stack** (only if `overfished-ml`, `overfished_api`, or `overfished_fetch_plugin` is missing) — `backend/requirements.txt` (Jinja2, LangChain for tools in the map API, `playwright` library, etc.), [ml/](ml/), `pip install -e "api[ml,dev]"`, [plugins/fetch_plugin/](plugins/fetch_plugin/) (agentic `/agent` when `AGENT_BACKEND=hybrid` — default in the script).
2. **Playwright Chromium** — `playwright install chromium` so on-demand and pre-rendered **PDFs** work (see [backend/documents/render.py](backend/documents/render.py)).
3. **ML smoke** — one synthetic RNN + BiLSTM + ensemble run so `torch` + [overfished-ml](ml/) is exercised the same way as the BFF [sequence routes](api/src/overfished_api/routers/sequence.py) (no extra HTTP process).
4. **PDF prerender** — `python -m documents.render` in [backend/](backend/) writes the demo IUU case family to `backend/output/…` (served as `/static` from the map API).
5. **Servers** — uvicorn on 8000 + 8001, then `npm run dev` in [frontend/](frontend/).

**Faster re-runs (skip heavy steps):** `STARTUP_QUICK=1 ./scripts/startup.sh` only starts the three long-running services. You can also set individually: `STARTUP_SKIP_PIP=1`, `STARTUP_SKIP_PLAYWRIGHT=1`, `STARTUP_SKIP_PDF_PRERENDER=1`, `STARTUP_SKIP_ML_SMOKE=1`. Optional: `STARTUP_INSTALL_LANGCHAIN_PLUGIN=1` adds the [langchain plugin](plugins/langchain_plugin/) for `AGENT_BACKEND=langchain`.

| Port | App |
|------|-----|
| 8000 | [backend/](backend/) `api.main` — map, cases, Twilio, fixtures, **static output / PDFs** (same routes the SPA calls via `/api/…` in dev). |
| 8001 | [api/](api/) `overfished_api` — `/agent`, `/ml/sequence/…`, `/audio`, Auth0. Proxied as `/agentapi/…` in [frontend/vite.config.ts](frontend/vite.config.ts). |
| 5173 | [frontend/](frontend/) Vite dev with codegen + [link-data](frontend/scripts/link-data.mjs) via `predev`. |

**One-time environment** (same venv is typical):

1. `python3 -m venv .venv && . .venv/bin/activate` (or your preferred venv)
2. Run `./scripts/startup.sh` once, or install manually: `pip install -r backend/requirements.txt`, `pip install -e "ml"`, `pip install -e "api[ml,dev]"`, `pip install -e "./plugins/fetch_plugin"`
3. Root [`.env`](.env) with Auth0, `USE_FIXTURES=1` for the demo, and any API keys you need; avoid committing secrets

If the BFF exits with `No module named 'fastapi_plugin'`, the Auth0 API shim is missing — `pip install -e "api"` (or re-run the installs above) pulls `auth0-fastapi-api` into the same venv. `Address already in use` on 8000/8001 means another `uvicorn` (or a prior `startup`); stop it or free those ports.

Optional: Databricks, GX10, or `overfished-pipeline` on large CSVs (see [data/local_pipeline/](data/local_pipeline/)) — not part of the default `startup` script.

## Repository layout

```text
frontend/                 Vite + React app
api/                      FastAPI BFF (routers + ports + deps)
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
| `VITE_API_URL` | Frontend | BFF base URL; empty = same-origin `/api` (Vite proxy in dev). |
| `VITE_AUTH0_DOMAIN` | Frontend | Auth0 tenant domain (no `https://`, e.g. `dev-6n2vvavwg11rnrx2.us.auth0.com`). |
| `VITE_AUTH0_CLIENT_ID` | Frontend | Auth0 SPA application Client ID. |
| `VITE_AUTH0_AUDIENCE` | Frontend | Custom API identifier, e.g. `https://overfished-bff` (not Management API). |
| `AUTH0_DOMAIN` / `AUTH0_AUDIENCE` | API (BFF) | Same as Vite; used for JWT validation. Or rely on Vite-prefixed vars if using one root `.env`. |
| `AUTH0_BYPASS` | API | `1` = skip JWT (e.g. tests); `0` = require Bearer token. |
| `CORS_ALLOW_ORIGINS` | API | Comma-separated if the SPA and API are on different origins. |
| `DATABRICKS_HOST` | Databricks CLI / jobs | Workspace host. |
| `DATABRICKS_TOKEN` | Databricks CLI / jobs | PAT (never commit). |
| `MLFLOW_TRACKING_URI` | ML jobs (optional) | Experiment tracking. |
| `GX10_HOST` | ML pipeline runtime | Remote host/IP for optional GX10 SSH execution. |
| `GX10_USER` | ML pipeline runtime | SSH user for GX10 execution. |
| `GX10_REMOTE_WORKDIR` | ML pipeline runtime | Remote directory where synced code/data are executed. |
| `GX10_SSH_KEY_PATH` | ML pipeline runtime (optional) | SSH private key path for GX10 auth. |
| `GX10_SSH_PORT` | ML pipeline runtime (optional) | SSH port (default `22`). |
| `VESSEL_IMAGE_OFFLINE` | ML image enrichment (optional) | Set `1` to use only cache/CSV/overrides (no MarineTraffic or Commons). |

### Auth0: "Client is not authorized to access resource server"

The **Custom API** is registered (e.g. audience `https://overfished-bff`), but the **SPA application** is not allowed to request tokens for it. This is fixed only in the [Auth0 Dashboard](https://manage.auth0.com/):

1. **APIs** → open the API whose **Identifier** exactly matches `VITE_AUTH0_AUDIENCE` / `AUTH0_AUDIENCE` (e.g. `https://overfished-bff`). Create it if missing.
2. **Applications** → your Single Page App (the **Client ID** in `.env`).
3. Open the **APIs** tab (or **API Authorization** in Settings, depending on UI) and **authorize** this application for that API, then save.

Use **Application type** = Single Page Application, **Token Endpoint Authentication** = None, and add `http://localhost:5173` to **Allowed Callback URLs**, **Allowed Logout URLs**, and **Allowed Web Origins**.

**`./scripts/startup.sh`:** Vite sends **`/api`** to the **demo map API** on port `8000` and **`/agentapi`** to the **Auth0 BFF** on port `8001`. Map/health/vessel data does not go through the BFF; only agent/ML (and any route under `/agentapi`) do. A **401** on an `/agentapi/*` call usually means a missing/invalid access token, not a bad `/api` setup.

**Still stuck?** Copy the full line from the browser (Auth0 error page, Network tab, or the app’s red sign-in error) when asking for help; “Callback URL mismatch”, `invalid_scope`, and `unauthorized` point to different dashboard fixes.

## Install and run (scaffold)

**Frontend**

```bash
cd frontend && npm install && npm run dev
```

**API**

```bash
cd api && pip install -e ".[dev]"
uvicorn overfished_api.main:app --reload --host 0.0.0.0 --port 8000
```

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

Install the ML package into the **same** venv the API uses, then restart uvicorn:

```bash
# from repo root, with .venv active
pip install -e "./ml[dev]"   # torch + overfished_ml; see [ml/README.md](ml/)
```

- **HTTP demo (browser or curl, ~10–20s first time):**  
  [http://127.0.0.1:8000/ml/sequence/demo](http://127.0.0.1:8000/ml/sequence/demo)  
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
