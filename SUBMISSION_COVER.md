# PolarityIQ Stage 1 Submission Cover

Owner: Hassan Asif  
Assessment date: 2026-05-17  
Submission target: `optimize@falconscaling.com`

## What To Open First

1. `fo_dataset_pipeline/reports/methodology_summary.md`  
   Human-validation narrative for how the dataset was built, where automation was trusted, and where it was not.

2. `fo_dataset_pipeline/reports/validation_chains.md`  
   Three source-to-field validation chains with quotes, uncertainty, and what would change the conclusion.

3. `reports/eval_report.md`  
   Honest 45-question RAG audit. It intentionally includes aliases, negative controls, multi-hop prompts, and typo probes; it is not an all-green showcase.

4. `src/ui/app.py` or the Streamlit demo  
   Evidence review console showing answer, missing data, caveats, citations, reasoning path, selected evidence, and other retrieved candidates.

5. `EFFORT_AND_AI_DISCLOSURE.md`  
   Time allocation and AI-vs-human disclosure.

## Submission Contents

- Dataset: `fo_dataset_pipeline/data/processed/family_offices_validated.xlsx`
- Dataset JSON/CSV: `fo_dataset_pipeline/data/processed/family_offices_validated.{json,csv}`
- Claim evidence: `fo_dataset_pipeline/data/processed/field_evidence.csv`
- Source registry: `fo_dataset_pipeline/data/processed/source_registry.csv`
- RAG app: `src/`, `scripts/`, `data/processed/`, `reports/eval_report.md`
- Demo UI: `streamlit run src/ui/app.py`

## Human Validation Layer Summary

The system is designed to show the reasoning between observation and answer:

- Every answer path is constrained to locked local evidence.
- Sensitive fields are copied only if directly present.
- Missing AUM, principal contact, and recent activity are abstained rather than inferred.
- SEC answers are phrased as dataset-snapshot claims, not legal conclusions.
- The eval report preserves known failures instead of hiding them.

## Known Limits I Would Prioritize Next

- Alias handling is incomplete for informal brand names such as "OG Wealth".
- City-level filters are weaker than state/country filters.
- The deterministic answerer does not compute true aggregates for multi-hop questions.
- Typo tolerance exists through retrieval but is not reliable enough to claim.
- Form ADV PDFs are referenced but not parsed into normalized fields.

## Demo Status

Local demo verified on `http://localhost:8501` with:

- Cat Trail entity lookup
- Ralph phone abstention
- Ohana SEC/CRD evidence
- Pathstone recent activity
- Filtered SEC California listing
- Cat Trail vs Ohana comparison

If a public deployment URL is not included in the submission email, include a screen recording demonstrating the same six paths.
