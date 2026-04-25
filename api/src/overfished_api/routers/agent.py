from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from overfished_api.deps import AgentBackendDep

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRunRequest(BaseModel):
    query: str = Field(..., min_length=1)
    context: dict[str, Any] | None = None


@router.post("/run")
async def run_agent(body: AgentRunRequest, backend: AgentBackendDep) -> dict[str, Any]:
    result = await backend.run(body.query, body.context)
    return {
        "status": result.status,
        "message": result.message,
        "detail": result.detail,
    }
