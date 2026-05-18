# Effort And AI Disclosure

## Time Allocation

Approximate focused effort for this Stage 1 submission:

| Workstream | Total | AI hrs | Human hrs | What AI helped with | What I owned / verified |
|---|---:|---:|---:|---|---|
| Dataset research and enrichment | 12.0 | 1.5 | 10.5 | Drafted scraper input shapes and repeatable promoter scaffolding. | Reviewed source acceptability, ran enrichment passes, checked URL/source evidence, chose blank-over-inferred fields. |
| Human validation review | 4.5 | 0.5 | 4.0 | Suggested validation-chain structure and boundary prompts. | Read the chains, resolved the JFG PDF and Verlinvest grid manually, decided what remained uncertain. |
| Evidence review workflow | 5.0 | 2.0 | 3.0 | Drafted query/review workflow scaffolding. | Designed safe-answer policy, sensitive-field abstention, and evidence-display acceptance thresholds. |
| UI and demo workflow | 3.0 | 1.0 | 2.0 | Assisted Streamlit layout rewrite. | Chose assessor workflow, verified evidence-first rendering and abstention scenarios. |
| Testing and evaluation | 4.5 | 1.0 | 3.5 | Generated edge-case review categories and candidate tests. | Kept documented boundaries visible, ran coverage/audit gates, and fixed regressions. |
| Documentation and submission packaging | 3.5 | 1.0 | 2.5 | Drafted first-pass packet sections. | Rewrote HVL trace, corrected stale paths, added falsification conditions, kept limitations explicit. |
| Final review | 2.5 | 0.5 | 2.0 | Helped cross-check path and metric consistency. | Rebuilt CSV/JSON/XLSX artifacts, reviewed git diff, and prepared the main-branch submission packet. |

Estimated total: 35.0 hours.

## AI-Assisted Work

AI was used as an implementation and review assistant for:

- Drafting repeatable Python pipeline code.
- Generating first-pass tests and edge-case prompts.
- Refactoring the Streamlit UI around an assessor workflow.
- Expanding evidence-review scenarios and report format.
- Drafting submission-package documents.

AI was not treated as a factual source. A value entered the dataset only when a cited source, local evidence artifact, or deterministic parser supported it.

## Human-Owned Work

Human judgment was required for:

- Choosing which sources were acceptable evidence.
- Deciding when a field should remain blank instead of inferred.
- Reviewing source conflicts, especially contact and Google Places phone conflicts.
- Setting the safe-answer policy for principal contact fields, AUM, SEC status, and recent activity.
- Selecting which review boundaries to preserve instead of overfitting the submission narrative.
- Rejecting broad principal LinkedIn name matches when the official page did not link the profile.
- Choosing the official/contact-source phone as canonical for the 6 Google Places conflicts while flagging the disagreement.

## Disclosure Boundary

The submitted dataset and screen-recording outputs should not be read as autonomous AI claims. They are evidence-bound artifacts built with automation but constrained by explicit human validation rules. Where the evidence was missing or ambiguous, the intended behavior is to abstain or state the uncertainty.
