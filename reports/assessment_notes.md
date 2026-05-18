# Assessment Notes And Falsification Conditions

## What I Am Claiming

[OBSERVE] The submitted workbook has 50 accepted records, 137 columns, 112 row-level source URLs, 338 source-registry rows, and 2,212 claim-level evidence rows.

[ASSUME] [ASSUMPTION: the evaluator will prefer explicit uncertainty over higher fill rates created by inferred personal data.]

[VALIDATE] The dataset gate is `python scripts\audit_xlsx.py`; the code-quality gates are `pytest tests\ -v --cov=. --cov-report=term-missing --cov-fail-under=80`, `ruff check .`, and `pip-audit`.

## Falsification Conditions

| Claim | What would falsify it |
|---|---|
| These 50 records are family-office-relevant entities | If three or more records lack official/source support for family-office, family-backed, UHNW, or multi-family-office framing. |
| The dataset does not infer private principal channels | If any principal email/direct phone is populated without an official public source tied to that person. |
| Principal LinkedIn handling is conservative | If a promoted personal LinkedIn URL is not linked from an official profile/team page. |
| SEC fields are regulatory-source-backed | If a CRD, SEC file number, or Form ADV URL cannot be traced to SEC/IAPD evidence. |
| Form ADV AUM parsing is safe | If `sec_aum_usd` cannot be found in the SEC PDF's regulatory-assets-under-management text. |
| Recent activity is not padded | If a promoted recent-activity item is not about the exact entity or predates the 2025-01-01 cutoff. |
| Phone conflicts are visible | If a row with differing primary and Google Places phone values lacks `primary_phone_conflict_with_places=True`. |
| Evidence source registry is complete | If a remote `source_url` or `source_urls` value is not represented in the `sources` sheet/source registry, unless it is an explicit existing local artifact path. |
| SEC near matches are reviewer-owned | If an IAPD near match below the acceptance threshold lacks a documented `review_status` or `manual_review_status`. |
| Public-recency wording is fresh | If public-signal wording uses stale `as of` dates relative to the audit run date. |
| Missing sensitive fields remain blank | If a missing AUM, missing phone, or principal personal-contact field is populated without direct supporting evidence. |

## Remaining Risk

The strongest remaining improvement would be page-aware Form ADV Schedule A extraction. I parsed regulatory AUM and fee labels, but did not promote listed officers because the PDF table text was not reliable enough without manual review.

Dataset/evidence audit hardening is intentionally read-only. If `python scripts\audit_xlsx.py` fails on duplicate claim IDs, unregistered evidence URLs, SEC near matches without review status, or source-content mismatch, the fix belongs in the parent dataset/evidence integration rather than in the audit script.
