# Assessment Notes

## Assumptions

- The JSON file at `fo_dataset_pipeline/data/processed/family_offices_validated.json` is the canonical machine-readable locked dataset.
- The XLSX file is used as a parity check for row and column shape.
- Local-first means no paid APIs, hosted vector database, hosted tracing, or live enrichment during answer time.
- Empty sensitive fields mean “not evidenced in the locked dataset,” not “unknown but inferable.”

## Engineering Judgment

This repository optimizes for evidence visibility rather than generative polish. ChromaDB is used for local dense retrieval, BM25 is kept separate for exact lexical matching, and deterministic extraction is the default answer mode. The optional local LLM path is deliberately downstream of evidence selection and is rejected if it introduces new sensitive-looking tokens.

## Falsifiable Choices

- Dataset contract: exactly 50 rows and 116 columns.
- Chunk counts: one profile, contact-policy, and regulatory chunk per accepted record; recent-activity chunks only when evidence exists.
- Sensitive-field behavior: missing phone, principal LinkedIn, AUM, SEC, and recent activity must abstain or caveat rather than invent.
- Citation behavior: non-abstained answers must include retrieved record citations where source URLs are available.
- Eval behavior: the 20-question golden set measures hit@3, MRR, record recall@5, citation accuracy, unsupported claims, abstention accuracy, and missing-data honesty.

## Limitations

- The system does not perform live verification after the validation snapshot.
- The embedding model may need a one-time free model download unless already cached locally.
- A deterministic hashing embedder is available as a last-resort fallback for runnability, but BGE/MiniLM embeddings are preferred.
- The UI is designed for assessment review, not production access control.

## Validation Commands

```powershell
python scripts\build_all.py
pytest tests\ -v --cov=. --cov-report=term-missing --cov-fail-under=80
ruff check .
pip-audit -r requirements.txt
python -m src.eval.run_eval --eval data\processed\golden_eval.jsonl --out reports\eval_report.md
```
