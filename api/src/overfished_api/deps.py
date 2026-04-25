from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends

from overfished_api.ports.agent import AgentBackend, AgentRunResult
from overfished_api.settings import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()


class NoOpAgentBackend:
    """Default agent binding: no LLM, no external agent calls."""

    async def run(self, query: str, context: dict[str, Any] | None = None) -> AgentRunResult:
        _ = (query, context)
        return AgentRunResult(
            status="noop",
            message="Agent backend not configured (AGENT_BACKEND=noop).",
            detail={},
        )


def get_agent_backend(settings: Annotated[Settings, Depends(get_settings)]) -> AgentBackend:
    if settings.agent_backend.lower() == "langchain":
        from overfished_langchain_plugin.factory import build_agent_backend

        return build_agent_backend()
    return NoOpAgentBackend()


AgentBackendDep = Annotated[AgentBackend, Depends(get_agent_backend)]
