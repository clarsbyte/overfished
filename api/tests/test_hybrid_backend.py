from __future__ import annotations

import asyncio
from typing import Any

from overfished_api.hybrid_backend import HybridAgentBackend, HybridConfig
from overfished_api.ports.agent import AgentRunResult


class _SuccessBackend:
    async def run(self, query: str, context: dict[str, Any] | None = None) -> AgentRunResult:
        return AgentRunResult(status="ok", message=f"handled:{query}", detail={"source": "fetch"})


class _SlowBackend:
    async def run(self, query: str, context: dict[str, Any] | None = None) -> AgentRunResult:
        _ = (query, context)
        await asyncio.sleep(0.05)
        return AgentRunResult(status="late", message="late", detail={})


class _ErrorBackend:
    async def run(self, query: str, context: dict[str, Any] | None = None) -> AgentRunResult:
        _ = (query, context)
        raise RuntimeError("boom")


class _FallbackBackend:
    async def run(self, query: str, context: dict[str, Any] | None = None) -> AgentRunResult:
        return AgentRunResult(status="fallback", message=f"fallback:{query}", detail={"source": "langchain"})


def test_fetch_success_path() -> None:
    backend = HybridAgentBackend(
        fetch_backend=_SuccessBackend(),
        fallback_backend=_FallbackBackend(),
        config=HybridConfig(fetch_timeout_seconds=0.01, fetch_max_retries=1, fetch_enabled=True),
    )
    result = asyncio.run(backend.run("hello"))
    assert result.status == "ok"
    assert result.detail["hybrid"]["route"] == "fetch"
    assert result.detail["hybrid"]["fallback_reason"] is None


def test_fetch_timeout_falls_back() -> None:
    backend = HybridAgentBackend(
        fetch_backend=_SlowBackend(),
        fallback_backend=_FallbackBackend(),
        config=HybridConfig(fetch_timeout_seconds=0.001, fetch_max_retries=1, fetch_enabled=True),
    )
    result = asyncio.run(backend.run("hello"))
    assert result.status == "fallback"
    assert result.detail["hybrid"]["route"] == "fallback"
    assert result.detail["hybrid"]["fallback_reason"] == "fetch_timeout"


def test_fetch_and_langchain_unavailable_returns_noop_like_fallback() -> None:
    class _NoOpFallback:
        async def run(self, query: str, context: dict[str, Any] | None = None) -> AgentRunResult:
            _ = (query, context)
            return AgentRunResult(
                status="noop",
                message="Agent backend not configured (AGENT_BACKEND=noop).",
                detail={},
            )

    backend = HybridAgentBackend(
        fetch_backend=_ErrorBackend(),
        fallback_backend=_NoOpFallback(),
        config=HybridConfig(fetch_timeout_seconds=0.01, fetch_max_retries=1, fetch_enabled=True),
    )
    result = asyncio.run(backend.run("hello"))
    assert result.status == "noop"
    assert result.detail["hybrid"]["route"] == "fallback"
    assert result.detail["hybrid"]["fallback_reason"] == "fetch_error"
