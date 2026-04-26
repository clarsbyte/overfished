import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# overfished_api → src → api → monorepo root; load so uvicorn CWD can be any folder.
_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT / ".env")
load_dotenv(_ROOT / "api" / ".env", override=True)  # optional BFF-only overrides
load_dotenv(override=True)  # CWD .env

from overfished_api.auth import cors_allowed_origins, protected_route_dependencies  # noqa: E402
from overfished_api.routers import agent, comms, datasets, health, regions, sequence, vessels  # noqa: E402


def create_app() -> FastAPI:
    app = FastAPI(title="Overfished API", version="0.1.0")

    # When the SPA and API are on different origins, set e.g. CORS_ALLOW_ORIGINS=https://app.example.com
    origins = cors_allowed_origins()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    audio_dir = Path(os.getenv("AUDIO_OUTPUT_DIR", "audio_output"))
    audio_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/audio", StaticFiles(directory=str(audio_dir)), name="audio")

    protected = protected_route_dependencies()

    app.include_router(health.router)
    app.include_router(datasets.router, dependencies=protected)
    app.include_router(regions.router, dependencies=protected)
    app.include_router(vessels.router, dependencies=protected)
    app.include_router(agent.router, dependencies=protected)
    app.include_router(sequence.router, dependencies=protected)
    app.include_router(comms.router, dependencies=protected)
    return app


app = create_app()
