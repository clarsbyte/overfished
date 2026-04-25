# overfished-api

FastAPI BFF scaffold. Routers are stubs; ports define extension points.

Install:
```
pip install -e ".[dev]"
pip install -r ../backend/requirements.txt   # for /agent/* endpoints
```

Run: `uvicorn overfished_api.main:app --reload`

## Agent endpoints

The four backend LangChain agents are wired in via `routers/agent.py`:

| Endpoint | Backend agent | Body |
|----------|---------------|------|
| `POST /agent/gfw` | `gfw_agent.classify_vessel` | `{ "query": "<MMSI/IMO/name>", "days_back": 365 }` |
| `POST /agent/vessel` | `vessel_agent.run_agent` | `{ "latitude": <y>, "longitude": <x>, "radius_miles": 100 }` |
| `POST /agent/law` | `regional_agent.evaluate_point` / `evaluate_region` | `{ "latitude": <y>, "longitude": <x> }` or `{ "region_id": "<id>" }` (optional `port_country_code`, `vessel_flag`, `gear`, `species`) |
| `POST /agent/complete` | `pipeline_agent.evaluate_incident` | `{ "latitude": <y>, "longitude": <x>, "radius_miles": 50, "port_country_code": null, "mmsi": null }` |

Each call blocks the worker thread for 30 s – 2 min while the LangChain
agent loops; FastAPI runs them in `asyncio.to_thread` so the event loop
stays free. Responses are JSON: `{ "agent": ..., "output": "<verdict text>" }`.

The router puts `../backend` on `sys.path` and loads `../backend/.env`
at import — so `ANTHROPIC_API_KEY`, `GFW_API_KEY`, `AISSTREAM_API_KEY`,
etc. should live in `backend/.env` (already the case).

See the repository [README.md](../README.md) for vision, RACI, and env vars.
