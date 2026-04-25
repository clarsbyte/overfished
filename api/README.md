# overfished-api

FastAPI BFF for the Overfish AI vessel-monitoring stack. The frontend talks
to this API; this API talks to the backend agents (`../backend/`) and to
external services (Twilio, ElevenLabs, GFW, AISStream, Anthropic).

Install:
```
pip install -e ".[dev]"
pip install -r ../backend/requirements.txt   # for /agent/* and /comms/* endpoints
```

Run: `uvicorn overfished_api.main:app --reload --port 8000`

OpenAPI docs render at `http://localhost:8000/docs`.

## Endpoint overview

| Method | Path | Purpose |
|--------|------|---------|
| GET    | `/health` | Liveness probe. |
| GET    | `/regions/{region_id}` | Stub — returns `not_implemented`. |
| GET    | `/vessels/{vessel_id}` | Stub — returns `not_implemented`. |
| POST   | `/agent/run` | Pluggable backend agent (legacy). |
| POST   | `/agent/gfw` | GFW IUU classification for one vessel. |
| POST   | `/agent/vessel` | AIS lookup near a coordinate. |
| POST   | `/agent/law` | Citation-backed legal dossier. |
| POST   | `/agent/complete` | Full multi-agent vessel-incursion pipeline. |
| POST   | `/comms/call` | Pre-rendered ElevenLabs MP3 + Twilio playback. |
| POST   | `/comms/ai-call` | Claude-Haiku conversational call grounded in a case PDF. |
| POST   | `/twilio/voice/start` | Twilio webhook (internal — TwiML for call connect). |
| POST   | `/twilio/voice/respond` | Twilio webhook (internal — TwiML per user speech turn). |

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
at import — so `ANTHROPIC_API_KEY`, `GFW_API_ACCESS_TOKEN`,
`AISSTREAM_API_KEY`, etc. should live in `backend/.env` (already the case).

## Comms endpoints — vessel warning calls

Two flows:

- **`POST /comms/call`** — generates an ElevenLabs MP3 warning, uploads it
  to a public file host (catbox.moe → 0x0.st fallback), and places a
  Twilio call that `<Play>`s it once. Single-shot.

  ```json
  {
    "vessel_name": "LU RONG YUAN YU 666",
    "mmsi": "412345678",
    "violations": "AIS-disabled transit inside Galápagos Marine Reserve.",
    "phone_number": "+16198871884"
  }
  ```

  Returns `{ "status": "calling", "message": ..., "audio_url": ..., "call_sid": ... }`.

- **`POST /comms/ai-call`** — Claude-Haiku-powered dialog. The vessel hears
  a fixed warning ("Warning. Ship NAME is at high risk of illegal
  fishing.") and is then handed to Claude, which answers questions
  strictly from the case's evidence PDF
  (`backend/output/<case_id>/<doc>`).

  ```json
  {
    "to_number": "+16198871884",
    "vessel_name": "LU RONG YUAN YU 666",
    "mmsi": "412345678",
    "case_id": "SCB-2026-0425-001",
    "doc": "cease_and_desist_order.pdf",
    "public_base_url": "https://abc123.ngrok-free.dev"
  }
  ```

  | Field | Required | Default |
  |---|---|---|
  | `to_number` | yes | — |
  | `vessel_name` | no | `"Unknown Vessel"` |
  | `mmsi` | no | `"000000000"` |
  | `case_id` | no | `"SCB-2026-0425-001"` |
  | `doc` | no | `"cease_and_desist_order.pdf"` |
  | `public_base_url` | yes (or set `PUBLIC_BASE_URL` env) | — |

  `public_base_url` must be reachable from the public internet — Twilio
  cannot reach localhost. Use ngrok (`ngrok http 8000`), cloudflared, or a
  hosted deploy.

  Returns:

  ```json
  {
    "call_sid": "CA22c778652c610144fa285c6cb2d578d5",
    "webhook_url": "https://.../twilio/voice/start?vessel_name=...&mmsi=...",
    "vessel_name": "...",
    "mmsi": "...",
    "case_id": "...",
    "doc": "..."
  }
  ```

### Twilio webhooks (internal)

`/twilio/voice/start` and `/twilio/voice/respond` exist for Twilio to call
during an active `/comms/ai-call` — **not** for direct frontend use. They
return TwiML (XML) and parse Twilio's `application/x-www-form-urlencoded`
webhook bodies. Conversation state is held in-memory in
`backend/comms_lookup.py` (`_CALL_SESSIONS`, keyed by Twilio CallSid).

### Local testing without Twilio

`backend/test_ai_call.py` exposes the AI-call dialog as a REPL or a
TestClient webhook replay — no Twilio account or ngrok required:

```bash
cd ../backend
python test_ai_call.py            # interactive REPL
python test_ai_call.py --webhook  # replay the TwiML round-trip
```

## Required env vars

Set in `backend/.env`:

| Variable | Used by |
|---|---|
| `ANTHROPIC_API_KEY` | `/agent/*`, `/comms/ai-call` |
| `GFW_API_ACCESS_TOKEN` | `/agent/gfw`, `/agent/complete` |
| `AISSTREAM_API_KEY` | `/agent/vessel`, `/agent/complete` |
| `ELEVENLABS_API_KEY` | `/comms/call` |
| `TWILIO_ACCOUNT_SID` | `/comms/call`, `/comms/ai-call` |
| `TWILIO_AUTH_TOKEN` | `/comms/call`, `/comms/ai-call` |
| `TWILIO_FROM_NUMBER` | `/comms/call`, `/comms/ai-call` |
| `PUBLIC_BASE_URL` | optional default for `/comms/ai-call` |

## Conventions

- **Error responses** follow FastAPI defaults: `{"detail": "..."}` for
  4xx/5xx. 422 for Pydantic validation, 500 for backend import failures,
  502 for backend agent runtime failures, 400 for missing required fields
  like `to_number` / `public_base_url`.
- **Long-running** endpoints (`/agent/vessel`, `/agent/complete`) block —
  the frontend should show a loading state. Typical latencies: GFW
  classification 30–60 s, full pipeline 60–120 s.
- **Backend imports are lazy** inside route handlers. The API still boots
  if a backend module has missing deps; the failure surfaces only when its
  endpoint is called (as a 500 with the import error text).
- **CORS** is wide-open in dev — locked down before any hosted deploy.

See the repository [README.md](../README.md) for vision, RACI, and env vars.
