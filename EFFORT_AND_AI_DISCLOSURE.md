# Effort And AI Disclosure

## Time Allocation

Approximate focused effort for this Stage 1 submission:

| Workstream | Hours | Notes |
|---|---:|---|
| Dataset research and enrichment | 12.0 | Source discovery, crawl/export review, confidence scoring, workbook rebuild. |
| Human validation review | 4.0 | Manual audit notes, validation chains, uncertainty checks, source-quality decisions. |
| RAG build | 5.0 | Chunking, BM25, dense index, intent classification, deterministic answer paths. |
| UI and demo workflow | 3.0 | Streamlit evidence review console and scenario checks. |
| Testing and evaluation | 4.0 | Unit tests, coverage, 45-question adversarial eval, pip audit. |
| Documentation and submission packaging | 3.0 | Methodology, cover, effort disclosure, README links. |
| Final review | 2.0 | Re-run gates, inspect known limits, prepare branch/submission. |

Estimated total: 33.0 hours.

## AI-Assisted Work

AI was used as an implementation and review assistant for:

- Drafting repeatable Python pipeline code.
- Generating first-pass tests and edge-case prompts.
- Refactoring the Streamlit UI around an assessor workflow.
- Expanding the RAG golden set and report format.
- Drafting submission-package documents.

## Human-Owned Work

Human judgment was required for:

- Choosing which sources were acceptable evidence.
- Deciding when a field should remain blank instead of inferred.
- Reviewing source conflicts, especially contact and Google Places phone conflicts.
- Setting the safe-answer policy for principal contact fields, AUM, SEC status, and recent activity.
- Selecting which eval failures to preserve as honest limitations rather than patching around them.

## Disclosure Boundary

The submitted dataset and RAG outputs should not be read as autonomous AI claims. They are evidence-bound artifacts built with automation but constrained by explicit human validation rules. Where the evidence was missing or ambiguous, the intended behavior is to abstain or state the uncertainty.
