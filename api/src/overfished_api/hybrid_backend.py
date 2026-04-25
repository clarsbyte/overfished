from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from overfished_api.ports.agent import AgentBackend, AgentRunResult


@dataclass(frozen=True, slots=True)
class HybridConfig:
    fetch_timeout_seconds: float = 2.5
    fetch_max_retries: int = 1
    fetch_enabled: bool = True


class HybridAgentBackend:
    """Try Fetch backend first, then deterministically fall back."""

    def __init__(
        self,
        *,
        fetch_backend: AgentBackend | None,
        fallback_backend: AgentBackend,
        config: HybridConfig,
    ) -> None:
        self._fetch_backend = fetch_backend
        self._fallback_backend = fallback_backend
        self._config = config

    async def run(self, query: str, context: dict[str, Any] | None = None) -> AgentRunResult:
        started = time.perf_counter()
        fallback_reason = "fetch_disabled"
        fetch_attempts = 0
        last_fetch_error: str | None = None

        if self._config.fetch_enabled and self._fetch_backend is not None:
            for attempt in range(1, self._config.fetch_max_retries + 1):
                fetch_attempts = attempt
                try:
                    fetch_result = await asyncio.wait_for(
                        self._fetch_backend.run(query, context),
                        timeout=self._config.fetch_timeout_seconds,
                    )
                    return self._with_hybrid_detail(
                        fetch_result,
                        route="fetch",
                        fallback_reason=None,
                        fetch_attempts=fetch_attempts,
                        started=started,
                    )
                except asyncio.TimeoutError:
                    fallback_reason = "fetch_timeout"
                    last_fetch_error = "timeout"
                except Exception as exc:  # pragma: no cover - safety net around plugin code
                    fallback_reason = "fetch_error"
                    last_fetch_error = str(exc)
        elif self._fetch_backend is None:
            fallback_reason = "fetch_unavailable"

        fallback_result = await self._fallback_backend.run(query, context)
        return self._with_hybrid_detail(
            fallback_result,
            route="fallback",
            fallback_reason=fallback_reason,
            fetch_attempts=fetch_attempts,
            started=started,
            last_fetch_error=last_fetch_error,
        )

    def _with_hybrid_detail(
        self,
        result: AgentRunResult,
        *,
        route: str,
        fallback_reason: str | None,
        fetch_attempts: int,
        started: float,
        last_fetch_error: str | None = None,
    ) -> AgentRunResult:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        detail = dict(result.detail)
        detail["hybrid"] = {
            "route": route,
            "fallback_reason": fallback_reason,
            "fetch_attempts": fetch_attempts,
            "elapsed_ms": elapsed_ms,
            "last_fetch_error": last_fetch_error,
        }
        return AgentRunResult(status=result.status, message=result.message, detail=detail)
