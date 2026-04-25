# Overfished

Surface illegal or high-risk fishing using vessel activity, regional regulations, and evidence-style artifacts suitable for enforcement demos (LA Hacks / hackathon scope).

## User journey (high level)

1. Draw or select a region on the map.
2. Inspect activity and heatmap-style signals (fused from external fishing-data APIs).
3. Optionally highlight SAR / computer-vision detections as a **showcase** narrative.
4. Produce narrative and artifacts (reports, simulated hail, etc.) via the API, optionally backed by an agent plugin.

## Honesty and scope

- External fishing APIs are **near-real-time**, not live; product copy should say so.
- Operational vessel detections may come from provider-classified data; custom CV (e.g. SAR / YOLO) is a **separate showcase path** documented in [ml/](ml/) and [databricks/](databricks/README.md).

## Stack and layers

| Layer | Location | Role |
|-------|----------|------|
| Presentation | [frontend/](frontend/) | Next.js UI; calls the BFF over HTTP only. |
| API (BFF) | [api/](api/) | FastAPI routes, OpenAPI, DI; **no** embedded business logic in this scaffold. |
| ML library (stubs) | [ml/](ml/) | CV / feature entrypoints reserved for Databricks-driven workflows. |
| Agent plugin (optional) | [plugins/langchain_plugin/](plugins/langchain_plugin/) | LangChain behind `AgentBackend`; install only when needed. |
| Databricks | [databricks/](databricks/) | Jobs, notebooks, MLflow / Unity Catalog; not the Next.js runtime. |

Architecture detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Repository layout

```text
frontend/                 Next.js app
api/                      FastAPI BFF (routers + ports + deps)
ml/                       Stub ML/CV package for Databricks alignment
plugins/langchain_plugin/ Optional LangChain implementation of AgentBackend
databricks/               Asset bundle placeholder + platform README
docs/                     Architecture notes
```

## Environment variables (names only)

Set these in deployment or `.env` for the API (see [api/](api/) when running locally). Do not commit secrets.

| Name | Used by | Purpose |
|------|---------|---------|
| `AGENT_BACKEND` | API | `noop` (default) or `langchain` to load the plugin. |
| `NEXT_PUBLIC_API_BASE_URL` | Frontend | Base URL for BFF requests. |
| `DATABRICKS_HOST` | Databricks CLI / jobs | Workspace host. |
| `DATABRICKS_TOKEN` | Databricks CLI / jobs | PAT (never commit). |
| `MLFLOW_TRACKING_URI` | ML jobs (optional) | Experiment tracking. |

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
