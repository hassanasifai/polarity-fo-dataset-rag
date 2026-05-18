# Assessment Notes

## Assumptions

- The JSON file at `fo_dataset_pipeline/data/processed/family_offices_validated.json` is the canonical machine-readable locked dataset.
- The XLSX file is used as a parity check for row and column shape.
- Local-first means no paid APIs, hosted vector database, hosted tracing, or live enrichment during answer time.
- Empty sensitive fields mean “not evidenced in the locked dataset,” not “unknown but inferable.”

## Engineering Judgment

This repository optimizes for evidence visibility rather than generative polish. ChromaDB is used for local dense retrieval, BM25 is kept separate for exact lexical matching, and deterministic extraction is the default answer mode. The optional local LLM path is deliberately downstream of evidence selection and is rejected if it introduces new sensitive-looking tokens.

## Falsification Conditions

| Claim | What would falsify it |
|---|---|
| Dataset contract is locked | Anything other than exactly 50 rows and 137 columns in `family_offices_validated.json` / XLSX `data_50`. |
| These rows are evidence-backed family-office records | Three or more rows fail official-site/source review or turn out to be generic RIAs with no family-office/UHNW-family framing. |
| RAG safely abstains on sensitive missing fields | Any golden or manual query for principal personal email/phone, missing AUM, or missing recent activity returns an inferred value. |
| Citations are trustworthy | A non-abstained answer lacks a citation when the supporting record has source URLs. |
| BGE-small + BM25 is sufficient for this corpus | Hit@3 drops below 0.85 on alias/spelling/entity categories in the adversarial eval. |
| Recent-activity answers are snapshot-bound | The UI or answer text implies live/current news beyond the 2026-05-17 validation snapshot. |
| Form ADV parsing is conservative | `sec_aum_usd` is populated from anything other than a reliable regulatory-AUM pattern in the SEC PDF text. |

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
