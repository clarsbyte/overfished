from typing import Any

from overfished_api.ports.agent import AgentBackend, AgentRunResult


class LangChainPluginBackend:
    """Scaffold backend: satisfies AgentBackend without invoking LangChain yet."""

    async def run(self, query: str, context: dict[str, Any] | None = None) -> AgentRunResult:
        _ = (query, context)
        return AgentRunResult(
            status="langchain_scaffold",
            message="LangChain plugin loaded; chains and tools are not implemented.",
            detail={"plugin": "overfished_langchain_plugin"},
        )


def build_agent_backend() -> AgentBackend:
    """Construct the agent implementation for DI (lazy-imported from api deps)."""
    return LangChainPluginBackend()
