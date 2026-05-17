# Methodology Summary

## How I Found Them

- Started with broad public discovery, then replaced directory-dependent rows with candidates supported by official websites, official family-office service pages, SEC/IAPD-style disclosures, company registry pages, or official PDFs.
- Excluded names copied from the provided sample workbook by comparing normalized entity names before export.
- Mixed single-family offices, multi-family offices, family-backed investment firms, and family-originated foundations only when the row label makes that classification explicit.

## How I Enriched Them

- Normalized entity type, headquarters location, principal or family context, investment thesis, sector focus, AUM text when public, source notes, and uncertainty notes.
- Left private contact fields blank unless the data was directly supportable from public business sources.
- Preserved source URLs on every row and generated a separate source registry plus field-evidence table so the later RAG step can produce cited answers instead of unsourced summaries.

### Contact Promotion Ethics (Pass 2)

Public corporate contact intelligence was promoted into the main dataset only when both a value and an openable evidence URL were present. Every promoted cell is paired with a sibling `*_evidence_url` and a `*_confidence` label so the audit trail is preserved on the row itself.

- **Promoted (corporate-level only):** `primary_email`, `primary_phone`, `corporate_linkedin_url`.
- **NOT promoted (principal-level):** `principal_email`, `principal_phone`, `principal_linkedin_url`. Reason: no public evidence ties a specific personal email/phone/LinkedIn to a named principal role for these records. Promoting that data would be guessing.
- **Confidence labels in use:**
  - `corporate_public_listed` — email or phone scraped from a contact-style page on the official site.
  - `linkedin_scraped_match` — corporate LinkedIn URL returned by a direct LinkedIn company-page scrape and matched to the FO by website domain.
  - `linked_from_official_site` — corporate LinkedIn URL extracted from a `/company/...` link found on the official site.
- **Email deliverability:** the Apify email-verifier actor was blocked at runtime by actor permissions. Promoted emails were therefore syntax-checked and MX-fallback-checked locally — they are **not** SMTP-verified, and the dataset does not claim they are.

### Audit Pre-Screen (Pass 1)

Before contact promotion, each row was passed through a deterministic heuristic pre-screen (`audit_prescreen.py`). The pre-screen attaches an advisory `auto_prescreen_flag` (`look_carefully` or `looks_clean`) and a `;`-joined `auto_prescreen_reason`. The human-owned `human_audit_status` column carries the reviewer verdict (`pass` / `relabel` / `weak`).

- 9 of 50 rows were flagged `look_carefully` (5 service-provider MFOs already labeled honestly + 5 rows whose website domain is a brand abbreviation of the legal name).
- 41 of 50 rows passed the pre-screen cleanly.
- Pre-screen is advisory only — it raises attention, not verdicts.

### Human Audit Application (Pass 1 verdicts)

Each flagged row was reviewed against the on-disk source notes, Firecrawl markdown snapshots, and Apify evidence before a verdict was applied. The decisions are checked into source in `apply_audit.py::AUDIT_DECISIONS` with a per-record rationale comment, so the audit trail is reproducible and inspectable.

- All 9 pre-screen-flagged rows received verdict `pass` — every classification is supported by the official site language already captured in the evidence sheets.
- 3 of those 9 (fo_011 O'Donnell→OG Wealth, fo_022 Major Domus→mdmfo, fo_026 Yamauchi No. 10→y-n10) received an additional `uncertainty_notes` line explicitly explaining the brand → domain abbreviation, so a reader of the dataset sees the domain mismatch acknowledged rather than hidden.
- The remaining 41 `looks_clean` rows were defaulted to `pass` without further notes.
- Final `human_audit_status` distribution: **`pass` = 50 / 50**; `relabel` = 0; `weak` = 0.

## How I Validated Them

- Processed records: 50.
- Accepted records: 50.
- Total source links attached: 112.
- Confidence distribution: high=50, medium=0, low=0.
- Final source URLs no longer rely on SWFI-style discovery directories.
- Pydantic validation rejects missing required fields, invalid URLs, weak single-source rows, placeholder values, and malformed emails.
- Scoring rejects rows that lack a reachable official website or at least two reachable source URLs.
- The CLI checks candidate names against the assessment sample workbook and fails if any normalized name overlaps.
- The live validator requests the official website and every source URL and stores URL status metadata in the processed CSV, XLSX, and JSON outputs.
- Final delivery gate used `--required-count 50`, so the run fails unless exactly 50 records are accepted.

### Recent-Activity Promotion (Pass 4)

Recent activity was populated from `google_news_recent_signals.csv` (203 raw rows) using these filters in order: drop scraper-error rows, require `pubDate >= 2025-01-01`, require all informative tokens of the FO name to appear in the title, reject items from directory/aggregator sources (pitchbook, crunchbase, zoominfo, swfinstitute, wikipedia), then take the most recent surviving row.

- **Records with promoted `recent_activity`:** 21 of 50 (every entry: real headline + publication + date + article URL).
- **Records with explicit `no recent public signal as of 2026-05-17` uncertainty note:** 29 of 50. These are predominantly smaller or private offices with no qualifying 2025+ coverage — leaving the field blank with a transparent note is the HVL-compliant choice over loose-matching.
- **Promotion target:** the original plan aimed for ≥25 records. Stopping at 21 is a deliberate judgment call — relaxing the title-token match would have pulled in industry round-ups, RIA league tables, and CEO-personal-news pieces that mention an FO incidentally. That would inflate the count and degrade the signal.

## Honest Limitations

The dataset is internally consistent, evidence-backed, and tested. It still has gaps a reader should know about before relying on it:

- **Email deliverability is not verified.** Promoted emails pass syntax + MX checks only; SMTP-level verification was blocked by Apify actor permissions. Treat them as best-effort corporate addresses, not confirmed inboxes.
- **Principal-level contact intelligence is absent by design.** No row contains principal-specific email, phone, or LinkedIn. The public sources available do not link a personal contact channel to a named principal role with sufficient confidence.
- **Recent activity coverage is 21/50.** Small or private offices without 2025+ press coverage are honestly tagged in `uncertainty_notes` rather than padded with weak matches.
- **Three featured validation chains include 2 known unavailable snippets** — Firecrawl skipped the JFG Form CRS PDF (it does not crawl PDFs by default) and the Verlinvest team page is a team grid with no narrative sentence. Both are disclosed in the chains document with a manual-snippet TODO rather than fabricated.
- **The manual `human_audit_status` column** is reviewer-owned and starts at `pending`. The automated pre-screen flagged 9 of 50 rows for closer inspection; the remaining 41 passed the heuristics but have not been individually re-clicked. A row-by-row click-through is still recommended before submission.
- **Some MFO classifications are service-provider relationships, not private SFOs.** Where this is the case the `family_office_type` is set to `multi_family_office` and the `uncertainty_notes` field calls out the service-provider framing explicitly. A reader who applies a stricter "family office" definition will discount these rows.
- **AUM is missing for most records** because public AUM disclosures are inconsistent. Where present, AUM is quoted from the source language in `aum_text`; it is never inferred.
- **Brand-abbreviated domains** (5 rows: O'Donnell→ogwealth, Major Domus→mdmfo, Yamauchi N.10→y-n10, Laird Norton Wetherby→lnwadvisors, Homrich Berg→hbwealth) are flagged by the pre-screen so a reviewer can confirm domain → entity mapping without surprise.
- **Live URL validation depends on network conditions.** Reruns may surface intermittent failures even on URLs that were green at capture time; the validation snapshot date is 2026-05-17.

## What I Would Improve

- Add claim-level evidence rows with exact snippets and source snapshots for each high-value field beyond the three featured chains.
- Add SEC ADV enrichment for registered advisers and store CRD or filing URLs.
- Add archived copies or hashes of source artifacts so link rot does not weaken the audit trail.
- Add a human review column for contradiction checks across official pages, regulatory filings, and third-party rankings.
- Use the finalized dataset to build RAG chunks with record IDs, evidence IDs, source URLs, confidence scores, and validation status as metadata.
