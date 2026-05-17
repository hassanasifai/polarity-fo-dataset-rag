# PolarityIQ Stage 1 Submission Cover

Owner: Hassan Asif  
Assessment date: 2026-05-17  
Submission target: `optimize@falconscaling.com`

## What To Open First

1. `reports/methodology_summary.md`  
   Human-validation narrative for how the dataset was built, where automation was trusted, and where it was not.

2. `reports/validation_chains.md`  
   Three source-to-field validation chains with quotes, uncertainty, and what would change the conclusion.

3. `rag_demo/reports/eval_report.md`  
   Honest 45-question RAG audit. It intentionally includes aliases, negative controls, multi-hop prompts, and typo probes; it is not an all-green showcase.

4. `rag_demo/src/ui/app.py` or the Streamlit demo  
   Evidence review console showing answer, missing data, caveats, citations, reasoning path, selected evidence, and other retrieved candidates.

5. `EFFORT_AND_AI_DISCLOSURE.md`  
   Time allocation and AI-vs-human disclosure.

6. `reports/assessment_notes.md`  
   Falsification conditions: what would change my mind or invalidate key claims.

## Submission Contents

- Evaluator-friendly dataset CSV: `00_family_office_records.csv`
- Dataset workbook: `data/processed/family_offices_validated.xlsx`
- Dataset JSON/CSV: `data/processed/family_offices_validated.{json,csv}`
- Claim evidence: `data/processed/field_evidence.csv`
- Source registry: `data/processed/source_registry.csv`
- RAG app: `rag_demo/src/`, `rag_demo/scripts/`, `rag_demo/data/processed/`, `rag_demo/reports/eval_report.md`
- Demo UI: `cd rag_demo; streamlit run src/ui/app.py`
- Screen recording: `demo/task1_rag_walkthrough.mp4`
- GitHub branch: `https://github.com/hassanasifai/polarity-fo-dataset-rag/tree/hvl-submission-packet-20260517`

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
- Form ADV PDFs are parsed conservatively for SEC regulatory AUM and fee labels, but Schedule A officer parsing remains blank because the text patterns were not reliable enough to promote automatically.

## Demo Status

Local demo command:

```powershell
cd rag_demo
streamlit run src\ui\app.py
```

Verified scenarios:

- Cat Trail entity lookup
- Ralph phone abstention
- Ohana SEC/CRD evidence
- Pathstone recent activity
- Filtered SEC California listing
- Cat Trail vs Ohana comparison

The included `demo/task1_rag_walkthrough.mp4` is a 36-second local Streamlit walkthrough of the same six scenarios. For final email submission, upload that MP4 to an unlisted YouTube/Drive link or attach it if file-size policy allows.
