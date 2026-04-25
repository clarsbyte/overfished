# Architecture

This document supplements the root [README.md](../README.md).

## Layer diagram

```mermaid
flowchart TB
  subgraph presentation [Presentation]
    Next[Next.js_frontend]
  end
  subgraph api [API_BFF]
    Routes[FastAPI_routes]
    Ports[Ports_protocols]
  end
  subgraph plugins [Plugins_optional]
    LC[langchain_plugin]
  end
  subgraph databricks [Databricks]
    Jobs[Jobs_notebooks]
    MLflow[MLflow_UC]
  end
  Next -->|HTTP_JSON| Routes
  Routes --> Ports
  Ports -.->|AGENT_BACKEND_langchain| LC
  Jobs --> MLflow
  Routes -.->|config_uris| MLflow
```

## Dependency rule

- `overfished_api` defines **ports** (protocols) in `api/src/overfished_api/ports/`.
- `overfished_langchain_plugin` implements those ports and may depend on LangChain packages **only** inside the plugin package.
- The Next.js app must not import Python packages; it only consumes HTTP + env.

## ADRs

None yet. Add `docs/adr/NNNN-title.md` when you lock a contentious decision (e.g. auth, cache store).
