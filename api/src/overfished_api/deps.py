from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends

from overfished_api.hybrid_backend import HybridAgentBackend, HybridConfig
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
    mode = settings.agent_backend.lower()
    if mode == "langchain":
        from overfished_langchain_plugin.factory import build_agent_backend

        return build_agent_backend()
    if mode == "fetch":
        from overfished_fetch_plugin.factory import build_agent_backend

        return build_agent_backend()
    if mode in {"hybrid", "fetch_hybrid"}:
        fetch_backend = _try_build_fetch_backend()
        fallback_backend = _try_build_langchain_backend() or NoOpAgentBackend()
        return HybridAgentBackend(
            fetch_backend=fetch_backend,
            fallback_backend=fallback_backend,
            config=HybridConfig(
                fetch_timeout_seconds=settings.fetch_agent_timeout_seconds,
                fetch_max_retries=max(settings.fetch_agent_max_retries, 1),
                fetch_enabled=settings.fetch_agent_enabled,
            ),
        )
    return NoOpAgentBackend()


AgentBackendDep = Annotated[AgentBackend, Depends(get_agent_backend)]


def _try_build_langchain_backend() -> AgentBackend | None:
    try:
        from overfished_langchain_plugin.factory import build_agent_backend

        return build_agent_backend()
    except Exception:
        return None


def _try_build_fetch_backend() -> AgentBackend | None:
    try:
        from overfished_fetch_plugin.factory import build_agent_backend

        return build_agent_backend()
    except Exception:
        return None
