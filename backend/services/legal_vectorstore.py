"""Qdrant-backed retrieval of FAOLEX legal rules for the agent.

The agent process imports this module at boot. To keep that import light we
keep `qdrant-client` (small, pure-Python) in backend/requirements.txt and
lazy-import `sentence-transformers` inside the embedder helper. Hosts that
should serve RAG install backend/requirements-rag.txt; hosts that don't see
a graceful "RAG backend not installed" payload from query_rules.

Single-writer assumption: finetune.build_index is the only writer to the
local Qdrant store. The agent reads. Restart the agent process after a
rebuild because Qdrant local-mode opens the file tree exclusively on first
write.

Payload schema (one point per source sentence):
    {
        "country":         "ECU",                  # ISO3, indexed for filter
        "species":         ["yellowfin tuna"],
        "gear":            ["longline"],
        "zone":            ["EEZ"],
        "prohibition":     "...",
        "penalty_usd":     1200000 | null,
        "source_sentence": "...",                  # what gets embedded
        "source_doc":      "LEX-FAOC123456",
        "source_url":      "https://...",
        "confidence":      "silver" | "curated",
        "extracted_at":    "2026-04-25"
    }
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

COLLECTION = "faolex_rules"
DEFAULT_EMBED_MODEL = "law-ai/InLegalBERT"
FALLBACK_EMBED_MODEL = "sentence-transformers/all-mpnet-base-v2"
EMBED_DIM = 768  # both candidates produce 768-dim embeddings

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "qdrant_db"


@lru_cache(maxsize=4)
def get_client(path: str | None = None) -> QdrantClient:
    """Cached Qdrant client. Pass ":memory:" for tests."""
    if path == ":memory:":
        return QdrantClient(":memory:")
    target = Path(path) if path else DB_PATH
    target.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(target))


@lru_cache(maxsize=2)
def _get_embedder(model_name: str = DEFAULT_EMBED_MODEL):
    """Lazy-load sentence-transformers; fall back to a general model on failure."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RagBackendUnavailable(
            "sentence-transformers not installed. "
            "Run `pip install -r backend/requirements-rag.txt` to enable RAG."
        ) from exc

    try:
        return SentenceTransformer(model_name)
    except Exception:
        if model_name == DEFAULT_EMBED_MODEL:
            return SentenceTransformer(FALLBACK_EMBED_MODEL)
        raise


class RagBackendUnavailable(RuntimeError):
    """Raised when sentence-transformers/torch are not installed on this host."""


def embed_text(text: str, model_name: str = DEFAULT_EMBED_MODEL) -> list[float]:
    embedder = _get_embedder(model_name)
    return embedder.encode(text, normalize_embeddings=True).tolist()


def init_collection(client: QdrantClient | None = None) -> None:
    """Create (or reset) the FAOLEX rules collection. Idempotent."""
    c = client or get_client()
    if c.collection_exists(collection_name=COLLECTION):
        c.delete_collection(collection_name=COLLECTION)
    c.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
    )
    # Payload indexes are a no-op in local-mode Qdrant (file-backed); they
    # take effect only on the server. Setting the index anyway keeps the
    # collection schema portable to a server deployment without changes.
    try:
        c.create_payload_index(
            collection_name=COLLECTION,
            field_name="country",
            field_schema=PayloadSchemaType.KEYWORD,
        )
    except Exception:
        pass


def _stable_id(doc_id: str, idx: int) -> int:
    return abs(hash(f"{doc_id}::{idx}")) % (2**63 - 1)


def index_rules(
    rules: list[dict[str, Any]],
    country: str,
    doc_id: str,
    *,
    client: QdrantClient | None = None,
    model_name: str = DEFAULT_EMBED_MODEL,
) -> int:
    """Embed each rule's source_sentence and upsert with structured payload."""
    if not rules:
        return 0
    c = client or get_client()
    embedder = _get_embedder(model_name)

    sentences = [r.get("source_sentence", "") for r in rules]
    vectors = embedder.encode(sentences, normalize_embeddings=True, show_progress_bar=False)

    points: list[PointStruct] = []
    for i, (rule, vec) in enumerate(zip(rules, vectors)):
        payload = {**rule, "country": country, "source_doc": doc_id}
        points.append(PointStruct(id=_stable_id(doc_id, i), vector=vec.tolist(), payload=payload))

    c.upsert(collection_name=COLLECTION, points=points)
    return len(points)


def query_rules(
    query: str,
    country: str | None = None,
    top_k: int = 5,
    *,
    client: QdrantClient | None = None,
    model_name: str = DEFAULT_EMBED_MODEL,
) -> list[dict[str, Any]]:
    """Retrieve the most relevant indexed rules for a query.

    Returns a list of payload dicts (with `_score` added). Returns a single
    dict containing `error` if the RAG backend is unavailable, so callers
    can fail soft inside an agent tool.
    """
    try:
        query_vec = embed_text(query, model_name=model_name)
    except RagBackendUnavailable as exc:
        return [{"error": str(exc)}]

    c = client or get_client()
    flt = None
    if country:
        flt = Filter(must=[FieldCondition(key="country", match=MatchValue(value=country.upper()))])

    try:
        result = c.query_points(
            collection_name=COLLECTION,
            query=query_vec,
            query_filter=flt,
            limit=top_k,
            with_payload=True,
        )
        hits = result.points
    except Exception as exc:
        return [{"error": f"vectorstore unavailable: {exc!s}"}]

    out: list[dict[str, Any]] = []
    for h in hits:
        payload = dict(h.payload or {})
        payload["_score"] = float(h.score)
        out.append(payload)
    return out


def collection_count(client: QdrantClient | None = None) -> int:
    c = client or get_client()
    try:
        return int(c.count(collection_name=COLLECTION, exact=True).count)
    except Exception:
        return 0
