from fastapi import FastAPI

from overfished_api.routers import agent, health, regions, vessels


def create_app() -> FastAPI:
    app = FastAPI(title="Overfished API", version="0.1.0")
    app.include_router(health.router)
    app.include_router(regions.router)
    app.include_router(vessels.router)
    app.include_router(agent.router)
    return app


app = create_app()
