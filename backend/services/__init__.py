"""Runtime services consumed by the LangChain agent.

Currently:
  legal_vectorstore   Qdrant-backed FAOLEX rule retrieval (RAG).
  legal_extractor     Sentence-level NER → rule tuples (used offline by
                      finetune.extract_corpus and at request time when a
                      fine-tuned LegalBERT model is available locally).
"""
