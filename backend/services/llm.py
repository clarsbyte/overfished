"""Shared LLM factory with light/heavy model routing.

Two-tier routing — small structured agents (vessel_agent, gfw_agent) run on
the LIGHT model; the supervisor and regional dossier (pipeline_agent,
regional_agent) run on the HEAVY model. Tier is selected per call, not via
a single model env var.

Backend is selected via LLM_BACKEND env var:
  "ollama" (default) — ChatOllama against a local Ollama server
  "vllm"             — ChatOpenAI against a vLLM OpenAI-compatible server

Env overrides (all optional):
  LLM_BACKEND              "ollama" | "vllm" (default "ollama")
  OLLAMA_HOST              Ollama base URL (default http://localhost:11434)
  VLLM_HOST                vLLM base URL   (default http://localhost:8001)
  OLLAMA_MODEL             legacy fallback if a tier-specific var is unset
  OLLAMA_MODEL_LIGHT       default "gemma3:4b"
  OLLAMA_MODEL_HEAVY       default "gemma4:latest"
  VLLM_MODEL_LIGHT         default "google/gemma-3-27b-it"
  VLLM_MODEL_HEAVY         default "google/gemma-3-27b-it"
  OLLAMA_KEEP_ALIVE        default "30m" — keep models warm between calls
  OLLAMA_NUM_CTX           context window (default 16384)
  OLLAMA_NUM_THREAD        CPU threads (None = ollama default)
  OLLAMA_NUM_GPU           GPU layers (-1 = all, None = ollama default)
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

import requests

Tier = Literal["light", "heavy"]


def _llm_backend() -> str:
    return os.getenv("LLM_BACKEND", "ollama").lower()


def _ollama_base_url() -> str:
    return os.getenv("OLLAMA_HOST", "http://localhost:11434")


def _vllm_base_url() -> str:
    return os.getenv("VLLM_HOST", "http://localhost:8001") + "/v1"


def _model_for_tier(tier: Tier) -> str:
    if _llm_backend() == "vllm":
        default = "google/gemma-3-27b-it"
        if tier == "light":
            return os.getenv("VLLM_MODEL_LIGHT") or default
        return os.getenv("VLLM_MODEL_HEAVY") or default
    legacy = os.getenv("OLLAMA_MODEL")
    if tier == "light":
        return os.getenv("OLLAMA_MODEL_LIGHT") or legacy or "gemma3:4b"
    return os.getenv("OLLAMA_MODEL_HEAVY") or legacy or "gemma4:latest"


def _int_env(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _build_ollama_kwargs(num_predict: int | None) -> dict:
    kwargs: dict = {
        "temperature": 0,
        "base_url": _ollama_base_url(),
        "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
        "num_ctx": _int_env("OLLAMA_NUM_CTX") or 16384,
    }
    if num_predict is not None:
        kwargs["num_predict"] = num_predict
    n_thread = _int_env("OLLAMA_NUM_THREAD")
    if n_thread is not None:
        kwargs["num_thread"] = n_thread
    n_gpu = _int_env("OLLAMA_NUM_GPU")
    if n_gpu is not None:
        kwargs["num_gpu"] = n_gpu
    return kwargs


def build_chat_llm(tier: Tier, *, model: str | None = None, num_predict: int | None = None):
    """Build an LLM client for `tier`.

    Returns ChatOpenAI (vLLM backend) or ChatOllama (Ollama backend).
    Pass `model` to override the tier-resolved name. `num_predict` caps
    output tokens — only meaningful for Ollama; vLLM uses max_tokens.
    """
    resolved_model = model or _model_for_tier(tier)
    if _llm_backend() == "vllm":
        from langchain_openai import ChatOpenAI
        kwargs: dict = {
            "model": resolved_model,
            "base_url": _vllm_base_url(),
            "api_key": "none",
            "temperature": 0,
        }
        if num_predict is not None:
            kwargs["max_tokens"] = num_predict
        return ChatOpenAI(**kwargs)
    from langchain_ollama import ChatOllama
    return ChatOllama(model=resolved_model, **_build_ollama_kwargs(num_predict))


_WARMED: set[str] = set()


def _ping_model(model: str) -> None:
    if _llm_backend() == "vllm":
        # vLLM loads the model at server startup — no warm-up needed.
        return
    try:
        requests.post(
            f"{_ollama_base_url()}/api/generate",
            json={
                "model": model,
                "prompt": "",
                "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
            },
            timeout=120,
        )
    except Exception:
        pass


def warm_up_models(tiers: tuple[Tier, ...] = ("light", "heavy")) -> None:
    """Preload the requested tiers in parallel. Idempotent per process."""
    targets = [_model_for_tier(t) for t in tiers]
    pending = [m for m in targets if m not in _WARMED]
    if not pending:
        return
    with ThreadPoolExecutor(max_workers=len(pending)) as pool:
        list(pool.map(_ping_model, pending))
    _WARMED.update(pending)
