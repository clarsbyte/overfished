"""Plumbing tests for the FAOLEX RAG vectorstore.

Uses an in-memory Qdrant client and a deterministic fake embedder, so these
tests don't need torch/sentence-transformers/network. They verify that:
  - init_collection creates the collection + payload index
  - index_rules upserts with the documented payload shape
  - query_rules respects the country filter
  - count is consistent
"""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from services import legal_vectorstore as vs


class FakeEmbedder:
    """Deterministic 768-dim embedder with no model deps."""

    def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
        is_single = isinstance(texts, str)
        if is_single:
            texts = [texts]
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            arr = np.frombuffer(digest, dtype=np.uint8).astype(np.float32)
            tiled = np.tile(arr, (vs.EMBED_DIM // len(arr)) + 1)[: vs.EMBED_DIM]
            norm = np.linalg.norm(tiled) or 1.0
            vectors.append(tiled / norm)
        out = np.stack(vectors)
        return out[0] if is_single else out


@pytest.fixture
def vectorstore(monkeypatch):
    monkeypatch.setattr(vs, "_get_embedder", lambda *a, **kw: FakeEmbedder())
    vs.get_client.cache_clear()
    client = vs.get_client(":memory:")
    vs.init_collection(client=client)
    yield client
    vs.get_client.cache_clear()


def _rule(sentence: str, country: str, **extra) -> dict:
    return {
        "source_sentence": sentence,
        "country": country,
        "confidence": "silver",
        "species": extra.get("species", []),
        "gear": extra.get("gear", []),
        "zone": extra.get("zone", []),
        "prohibition": extra.get("prohibition", ""),
        "penalty_usd": extra.get("penalty_usd"),
    }


def test_index_and_count(vectorstore):
    n_esp = vs.index_rules(
        [_rule("Bluefin tuna purse seine fishing is prohibited in the Mediterranean.", "ESP")],
        country="ESP", doc_id="LEX-FAOC-ESP-001", client=vectorstore,
    )
    n_ecu = vs.index_rules(
        [_rule("Industrial trawling is banned within the Galápagos Marine Reserve.", "ECU")],
        country="ECU", doc_id="LEX-FAOC-ECU-001", client=vectorstore,
    )
    n_phl = vs.index_rules(
        [_rule("Longline fishing for tuna requires a permit in Philippine waters.", "PHL")],
        country="PHL", doc_id="LEX-FAOC-PHL-001", client=vectorstore,
    )
    assert (n_esp, n_ecu, n_phl) == (1, 1, 1)
    assert vs.collection_count(vectorstore) == 3


def test_country_filter(vectorstore):
    vs.index_rules(
        [_rule("A is prohibited.", "ESP"), _rule("B is prohibited.", "ESP")],
        country="ESP", doc_id="DOC-ESP", client=vectorstore,
    )
    vs.index_rules(
        [_rule("C is prohibited.", "PHL")],
        country="PHL", doc_id="DOC-PHL", client=vectorstore,
    )

    phl_hits = vs.query_rules("prohibition", country="PHL", top_k=5, client=vectorstore)
    assert len(phl_hits) == 1
    assert phl_hits[0]["country"] == "PHL"
    assert "_score" in phl_hits[0]

    all_hits = vs.query_rules("prohibition", country=None, top_k=5, client=vectorstore)
    assert len(all_hits) == 3


def test_payload_round_trips(vectorstore):
    rule = _rule(
        "Use of driftnets longer than 2.5 km is prohibited; penalty up to USD 50,000.",
        "ESP",
        gear=["driftnet"],
        prohibition="is prohibited",
        penalty_usd=50000,
    )
    vs.index_rules([rule], country="ESP", doc_id="LEX-X", client=vectorstore)
    hits = vs.query_rules("driftnet penalty", country="ESP", top_k=1, client=vectorstore)
    assert hits[0]["gear"] == ["driftnet"]
    assert hits[0]["penalty_usd"] == 50000
    assert hits[0]["prohibition"] == "is prohibited"
    assert hits[0]["confidence"] == "silver"


def test_query_returns_error_when_embedder_missing(monkeypatch, vectorstore):
    def boom(*args, **kwargs):
        raise vs.RagBackendUnavailable("sentence-transformers not installed")

    monkeypatch.setattr(vs, "embed_text", boom)
    out = vs.query_rules("anything", client=vectorstore)
    assert len(out) == 1 and "error" in out[0]
