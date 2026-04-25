"""Tool-shape test for the new query_faolex_rag agent tool.

Doesn't spin up the LLM — just verifies the tool's interface contract: it
accepts the documented args, calls into legal_vectorstore.query_rules, and
returns JSON-encoded payloads the LLM can quote.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def agent_module(monkeypatch):
    """Load regional_agent without performing the LangChain LLM init.

    ANTHROPIC_API_KEY is only checked inside build_agent_executor(), which we
    don't call here, so importing the module is safe.
    """
    import regional_agent
    return regional_agent


def test_query_faolex_rag_returns_json_list(agent_module, monkeypatch):
    fake_hits = [
        {
            "source_sentence": "Purse seine for bluefin tuna is prohibited.",
            "country": "ESP",
            "gear": ["purse seine"],
            "species": ["bluefin"],
            "confidence": "silver",
            "_score": 0.87,
        }
    ]
    monkeypatch.setattr(agent_module, "_query_rag_rules", lambda **kw: fake_hits)

    raw = agent_module.query_faolex_rag.invoke(
        {"query": "purse seine bluefin Mediterranean", "country_code": "ESP", "top_k": 3}
    )
    parsed = json.loads(raw)
    assert isinstance(parsed, list)
    assert parsed[0]["country"] == "ESP"
    assert parsed[0]["confidence"] == "silver"
    assert "source_sentence" in parsed[0]


def test_query_faolex_rag_swallows_backend_errors(agent_module, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("Qdrant unreachable")

    monkeypatch.setattr(agent_module, "_query_rag_rules", boom)
    raw = agent_module.query_faolex_rag.invoke({"query": "x"})
    parsed = json.loads(raw)
    assert "error" in parsed
    assert "Qdrant unreachable" in parsed["error"]
