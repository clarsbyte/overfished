from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    """Structured response from an agent run (stub fields only)."""

    status: str
    message: str
    detail: dict[str, Any]


@runtime_checkable
class AgentBackend(Protocol):
    """Pluggable agent surface (e.g. LangChain plugin implements this)."""

    async def run(self, query: str, context: dict[str, Any] | None = None) -> AgentRunResult:
        """Execute an agent turn; real implementations add tools and LLM calls."""
        ...
