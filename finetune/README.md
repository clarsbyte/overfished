# FAOLEX → LegalBERT → Qdrant RAG Pipeline

End-to-end: scrape FAOLEX → silver-label with Claude → fine-tune LegalBERT for NER → extract rule tuples → index in Qdrant → expose to the agent via `query_faolex_rag`.

The agent (`backend/regional_agent.py`) gets a new tool that retrieves semantically-relevant fisheries rules across **ECU, PHL, ESP, CHN, IDN** at request time. Rules retrieved this way are tagged `confidence: silver` to distinguish them from the curated cache (`confidence: curated`).

---

## Prerequisites

- Python 3.11+
- Anthropic API key (for the silver-labeling step) — set `ANTHROPIC_API_KEY` in your shell or in a `.env` file at the repo root or `finetune/`
- A GPU is recommended for training (CPU works for `--dry-run` only)

---

## Install

Two separate dependency sets, by design — the agent process stays light, the offline pipeline carries the heavy ML stack.

```bash
# Backend runtime (qdrant-client only — small, pure-Python)
cd backend
pip install -r requirements.txt

# Optional: enable RAG retrieval at runtime (sentence-transformers, transformers, torch).
# Without this, query_faolex_rag returns a graceful "RAG backend not installed" payload.
pip install -r requirements-rag.txt
```

```bash
# Offline pipeline (training, scraping, labeling, indexing)
cd finetune
pip install -e .

# Optional extras:
pip install -e .[lora]    # PEFT for the --lora training path
pip install -e .[render]  # playwright fallback for JS-rendered FAOLEX pages
```

If you installed `[render]`, you'll also need:

```bash
playwright install chromium
```

---

## Run order

The full pipeline. Each step is independently testable — start at any stage; downstream steps will tell you what's missing.

### 1. Fetch FAOLEX documents

```bash
# Default: all 5 countries, top 20 records each
python -m finetune.fetch_faolex

# Subset for a quick test
python -m finetune.fetch_faolex --countries ECU --max 3

# JS-rendered fallback (FAOLEX search results are client-rendered)
python -m finetune.fetch_faolex --render

# Already have manual HTML mirrors at finetune/data/raw/<ISO3>/manual/?
python -m finetune.fetch_faolex --parse-mirror
```

**Output:** `finetune/data/raw/<ISO3>/<LEX-FAOC-id>.json` (parsed) and `.html` (raw, for re-parsing).

**Seeding LEX-FAOC IDs:** FAOLEX search is JS-rendered, so the search step is best-effort. Drop known IDs into `finetune/data/seeds/<ISO3>.json` to give the scraper concrete starting points. Format documented in `finetune/data/seeds/README.txt`.

### 2. Silver-label with Claude

```bash
# Cheap dry-run on 5 sentences first — verify cache hits with ANTHROPIC_LOG=info
ANTHROPIC_LOG=info python -m finetune.auto_label --countries ECU --limit 5

# Full pass (capped at 300 sentences by default)
python -m finetune.auto_label

# Tighter cap
python -m finetune.auto_label --max-sentences 200
```

Uses `claude-opus-4-7` with adaptive thinking and prompt caching on the system+few-shot block. The first request writes the cache (~5K tokens at 1.25× cost), every subsequent sentence reads it at ~10× discount. ~300 sentences typically costs a few dollars.

**Output:** `finetune/data/silver/labels.jsonl` — one labeled sentence per line `{tokens, labels, doc_id, country, source}`.

### 3. Fine-tune LegalBERT

```bash
# Wiring smoke test — 5 steps on CPU, no GPU needed
python -m finetune.train --dry-run --device cpu

# Real run (default: full FT with embeddings + bottom 6 layers frozen)
python -m finetune.train

# LoRA path (smaller checkpoint, ~5-line config swap)
python -m finetune.train --lora

# Tune
python -m finetune.train --epochs 3 --batch-size 8 --learning-rate 2e-5
```

**Output:** `finetune/artifacts/legal_bert_ner/` (weights + tokenizer + label config).

**Expected runtime:** ~10–20 min on a single GPU with default settings (BERT-base, ~300 sentences, 5 epochs). The "3 hours" estimate from earlier planning was generous.

### 4. Evaluate

```bash
python -m finetune.eval
```

Reports per-label seqeval F1 on the held-out 20%. F1 ≥ 0.6 is the "useful" threshold (silver labels are noisy). If F1 < 0.5, fall back to stub mode in step 5.

### 5. Extract rule tuples

```bash
# Stub mode — keyword/regex spotter; works WITHOUT trained weights.
# Use this for end-to-end demo before training finishes.
python -m finetune.extract_corpus --mode stub

# NER mode — uses the fine-tuned model from step 3.
python -m finetune.extract_corpus --mode ner
```

**Output:** `finetune/data/extracted_rules.jsonl` — flat tuples matching the Qdrant payload schema (`species, gear, zone, prohibition, penalty_usd, source_sentence, country, source_doc, source_url, confidence`).

### 6. Build the Qdrant index

```bash
# Default embedder: law-ai/InLegalBERT (falls back to all-mpnet-base-v2 if unavailable)
python -m finetune.build_index

# Or pin a specific embedder
python -m finetune.build_index --model sentence-transformers/all-mpnet-base-v2
```

**Output:** populates `backend/data/qdrant_db/` (local file-mode Qdrant store, gitignored).

> ⚠️ **Restart the agent** after a rebuild — Qdrant local-mode uses a single-writer file lock, so the agent process needs to reopen its read handle.

### 7. Use it from the agent

The agent picks up the index automatically. From the backend dir:

```bash
# Direct CLI — point in CHN waters that misses the curated cache
python regional_agent.py 30.0 122.0 --port-country CHN

# Or via the API
# POST /agent/law  with {latitude, longitude, port_country_code, vessel_flag, gear, species}
```

Look in the trace for the `query_faolex_rag` tool call. The verdict should cite returned `source_sentence`s tagged as `confidence: silver`.

---

## Verify each layer

Quick smoke checks, each <30 s without a GPU:

```bash
# Step 1: scrape — expect a few JSON files
python -m finetune.fetch_faolex --countries ECU --max 3
ls finetune/data/raw/ECU/

# Step 5: stub extractor — expect tuples on test text
python -c "
import sys; sys.path.insert(0, 'finetune/src')
from finetune.extract_corpus import extract_rules_stub
text = 'Industrial trawling within marine reserves shall not be permitted; violators face penalties of up to USD 50,000.'
print(extract_rules_stub(text, country='ESP', source_doc='test', source_url=''))
"

# Vectorstore — runs in-memory with a fake embedder, no torch needed
cd backend
python -m pytest tests/test_legal_vectorstore.py -v

# Agent tool — mocked vectorstore, verifies the tool's interface
python -m pytest tests/test_regional_agent_rag.py -v

# Wiring smoke test for training
cd ..
python -m finetune.train --dry-run --device cpu
```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'qdrant_client'`** — install backend deps: `pip install -r backend/requirements.txt`.

**`RagBackendUnavailable: sentence-transformers not installed`** — the agent host needs the RAG extras: `pip install -r backend/requirements-rag.txt`.

**FAOLEX scrape returns 0 records** — search results are JS-rendered. Either:
1. Drop known LEX-FAOC IDs into `finetune/data/seeds/<ISO3>.json`, or
2. Run with `--render` (needs `pip install -e .[render]` and `playwright install chromium`), or
3. Hand-mirror HTML files into `finetune/data/raw/<ISO3>/manual/` and use `--parse-mirror`.

**`Fine-tuned weights not found at finetune/artifacts/legal_bert_ner/`** — either run `python -m finetune.train` first, or use stub mode: `python -m finetune.extract_corpus --mode stub`.

**Cache hit rate is zero in `auto_label.py`** — set `ANTHROPIC_LOG=info` and inspect the request. The system+few-shot block needs to be ≥4096 tokens to cache on Opus 4.7 (the included prompt is ~2.5K — if you trim it, you may fall below the threshold).

**Qdrant 1.17 errors about `.search()`** — the vectorstore uses the new `query_points` API; if you've forked the code, make sure you're on `qdrant-client>=1.9`.

**Tests in `test_documents.py` fail with `UnicodeDecodeError`** — pre-existing Windows cp1252 issue in the PDF rendering test, unrelated to this pipeline.

---

## What goes where

```
finetune/                          # Offline pipeline (this directory)
├── src/finetune/
│   ├── fetch_faolex.py            # Step 1: async scraper
│   ├── auto_label.py              # Step 2: Claude silver labeler
│   ├── dataset.py                 # Step 3a: HF Dataset + subword alignment
│   ├── train.py                   # Step 3b: Trainer scaffold
│   ├── eval.py                    # Step 4: seqeval F1
│   ├── extract_corpus.py          # Step 5: stub|ner extraction
│   └── build_index.py             # Step 6: → Qdrant
├── data/
│   ├── seeds/<ISO3>.json          # FAOLEX ID seed lists (committed)
│   ├── raw/<ISO3>/                # Scraped docs (gitignored)
│   ├── silver/labels.jsonl        # Silver labels (gitignored)
│   └── extracted_rules.jsonl      # Extracted tuples (gitignored)
├── artifacts/legal_bert_ner/      # Trained weights (gitignored)
└── pyproject.toml

backend/                           # Runtime
├── services/
│   ├── legal_vectorstore.py       # Qdrant CRUD, lazy embedder
│   └── legal_extractor.py         # NER-mode runtime extractor
├── data/qdrant_db/                # Local Qdrant store (gitignored)
├── regional_agent.py              # Agent — adds query_faolex_rag tool
├── regional_lookup.py             # Adds RAG hint to dossier "missing" array
├── requirements.txt               # Adds qdrant-client
└── requirements-rag.txt           # Optional: sentence-transformers + torch
```

---

## Demo line this unlocks

> "Our agent doesn't just prompt an LLM with raw law text — it retrieves semantically relevant rules from a knowledge base of fisheries regulations across 5 jurisdictions, extracted by a fine-tuned legal NER model, with provenance preserved end-to-end."
