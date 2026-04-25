"""Offline pipeline for the FAOLEX → LegalBERT → Qdrant RAG stack.

Modules:
  fetch_faolex     : async scrape FAOLEX (5 jurisdictions) → data/raw/<iso3>/
  auto_label       : Claude silver-labels sentences with BIO tags → data/silver/
  dataset          : JSONL → HF Dataset, subword-aligned token classification
  train / eval     : fine-tune nlpaueb/legal-bert-base-uncased → artifacts/legal_bert_ner/
  extract_corpus   : run NER (or stub regex) over raw docs → data/extracted_rules.jsonl
  build_index      : embed + upsert tuples into the Qdrant collection used by
                     backend.services.legal_vectorstore (collection: faolex_rules)
"""
