# Assessment Notes And Falsification Conditions

## What I Am Claiming

[OBSERVE] The submitted workbook has 50 accepted records, 133 columns, 112 source URLs, and 2,135 claim-level evidence rows.

[ASSUME] [ASSUMPTION: the evaluator will prefer explicit uncertainty over higher fill rates created by inferred personal data.]

[VALIDATE] The dataset gate is `python scripts\audit_xlsx.py`; the RAG gate is `cd rag_demo; python scripts\build_all.py; pytest tests\ -v --cov=. --cov-report=term-missing --cov-fail-under=80`.

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
| RAG abstention works | If a missing AUM, missing phone, or principal personal-contact prompt returns an invented value. |

## Remaining Risk

The strongest remaining improvement would be page-aware Form ADV Schedule A extraction. I parsed regulatory AUM and fee labels, but did not promote listed officers because the PDF table text was not reliable enough without manual review.
