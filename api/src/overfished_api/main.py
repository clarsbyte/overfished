import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

load_dotenv()  # Must run before routers are imported so module-level env vars resolve

from overfished_api.routers import agent, comms, health, regions, sequence, vessels


def create_app() -> FastAPI:
    app = FastAPI(title="Overfished API", version="0.1.0")

    audio_dir = Path(os.getenv("AUDIO_OUTPUT_DIR", "audio_output"))
    audio_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/audio", StaticFiles(directory=str(audio_dir)), name="audio")

    app.include_router(health.router)
    app.include_router(regions.router)
    app.include_router(vessels.router)
    app.include_router(agent.router)
    app.include_router(sequence.router)
    app.include_router(comms.router)
    return app


app = create_app()
