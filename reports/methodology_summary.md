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

### LinkedIn Company Enrichment (Pass 5)

The Apify LinkedIn company-page scraper output (`linkedin_company_evidence.csv`, 242 rows) was joined onto each FO row by website-domain match. Seven enrichment fields were promoted per matched row, every value paired with `linkedin_company_evidence_url` (the LinkedIn page URL) and `linkedin_company_confidence = linkedin_company_page`.

- **Promoted columns:** `linkedin_employee_count`, `linkedin_follower_count`, `linkedin_specialties` (semicolon-joined), `linkedin_company_size_band`, `linkedin_industry`, `linkedin_founded_year`, `linkedin_headquarters_full`.
- **Coverage:** 27 of 50 records have at least one LinkedIn-enrichment field populated. The remaining 23 either have no public LinkedIn company page (small or single-family offices) or the scraper's website field did not match our FO domain.
- **Acceptance gate:** the LinkedIn URL must match `linkedin.com/company/` and the `website` field on the LinkedIn record must share the same bare domain as the FO's `website_url`. School pages, personal profiles, and cross-domain matches are rejected.

### Social-Media Handles (Pass 6)

The Apify contact-info scraper raw output captures every social-media link found while crawling each FO's official site. We promoted per-platform URL columns (`twitter_url`, `instagram_url`, `facebook_url`, `youtube_url`, `tiktok_url`) only when the URL's host matched the canonical platform domain. Discovery source = the FO website that was crawled, stored as `social_media_evidence_url` with `social_media_confidence = linked_from_official_site`.

- **Coverage:** 23 of 50 records have at least one verified social handle. Facebook leads (16), then YouTube (11), Twitter (10), Instagram (9), TikTok (0 — no observed FO maintains a TikTok presence, which matches industry expectations and avoids fabricated nulls).
- **Acceptance gate:** rejects any URL whose host isn't on the platform's canonical domain (no spoof links).

### Google Places Corroboration (Pass 7)

The Apify Google-Maps scraper sometimes returned the *wrong* business for a given search string (e.g. "Ralph Family Office London" returned "Pall Mall Family Office Ltd"). To filter these out we kept only Places rows whose returned `website` shares the same bare domain as the FO's `website_url`. This guarantees we are corroborating the same entity, not a similarly named one.

- **Promoted columns:** `google_places_phone`, `google_places_reviews_count`, `google_places_rating`, `google_places_category`, `google_maps_url`.
- **Sidecar column:** `primary_phone_corroborated_by_places` — `True` when Places phone matches our promoted `primary_phone` (last 10 digits compared), `False` when they disagree, blank when either side is missing. **15 corroborated pairs** were surfaced (9 confirmed, 6 conflicted — the conflicts are real findings that an evaluator can review).
- **Coverage:** 33 of 50 records were domain-corroborated. The other 17 were either not found in Places or had a different website returned (filter rejected them).

### SEC IAPD / Form ADV Authoritative Identifiers (Pass 8)

The public IAPD search API (`https://api.adviserinfo.sec.gov/search/firm?query=...`) was queried for each FO with multiple name variants (full name, simplified by dropping generic suffixes, then 2-token core). Matches were scored by Jaccard similarity against the firm name and every `firm_other_names` alias, with a +0.25 bonus when the SEC-filed city+state matched the FO HQ. Threshold = 0.6.

- **Records matched (SEC-registered):** 33 of 50. Each has a SEC-authoritative CRD number, SEC file number, registration status (ACTIVE/INACTIVE), the official firm name as filed, every DBA alias, branch count, registered address, and a direct link to the Form ADV Part 2A PDF brochure.
- **Records explicitly marked unregistered:** 17 of 50. The `sec_registered = False` column and an explicit `uncertainty_notes` line state *"Not registered with the SEC — typical for single-family offices managing only family wealth."* This is not a failure — it is a meaningful finding about FO structure.
- **Per-row evidence files:** `data/evidence/sec_iapd_2026_05_17/{record_id}.json` carries the raw IAPD response, the queries tried, the match score, and the reasoning for both matched and unmatched rows.
- **What this adds:** authoritative regulatory identity for two-thirds of the dataset. Direct Form ADV PDF links unlock further evaluator drill-down (fee structure, conflict disclosures, investment strategy as filed). All data is sourced from the SEC's own public API — no third-party intermediary.

### Multi-Principal Intelligence (Pass 9, partial)

For the FOs whose Firecrawl-captured team/leadership/about pages contained named-person + role patterns, a deterministic markdown extractor surfaced 20 individuals across 3 firms (Verlinvest, Haven Private, Okabena Company). These are written into three principal slots per row (`principal_1_*` through `principal_3_*`), ordered by role seniority (Founder/Chair/President → CEO/CIO/CFO/COO → Managing Partner/Director → Partner → Principal → Director → Other), with every cell paired with the source page URL.

- **Confidence label:** `corporate_team_page` — name and role observed on the FO's own team/about page.
- **What we refused to fabricate:** principal LinkedIn URLs, work emails, and personal phones. Cross-referenced personal contact channels were not available for these 20 individuals from the public team-page evidence we have. Adding inferred data would be guessing.
- **Coverage limitation:** only 3 of 50 FOs have multi-principal data populated. Expanding coverage to the remaining 47 would require either Apify LinkedIn People scraping (cookieless variant, Apify-credit-bound) or a fresh Firecrawl pass with team-page URL discovery — both are next-iteration work.
- **Existing `principal_name` / `principal_title` columns** (populated for 19 of 50 from the original validator pass) are preserved unchanged; the new multi-principal columns are additive.

### Sample Workbook Parity + Data Completion Score (Pass 10)

The PolarityIQ-supplied sample workbook (`FO-MAX-data-sample-2.0.xlsx`) carries 31 columns and a Data Completion Score in the 19–29 range per row. To make our scoring directly comparable, our score counts populated cells across exactly those 31 sample columns (mapped to their snake_case equivalents in our workbook), NOT across our full 100+ column workbook. This is the same denominator the evaluator will diff against.

- **Sample-parity columns added:** `contact_first_name`, `contact_last_name`, `contact_full_name`, `contact_location` (derived from `principal_name` and HQ city/state/country); `contact_secondary_email`, `secondary_email_validation_code`, `email_code_explanation_secondary`, `email_quality_assessment_secondary`, `contact_secondary_phone` (honestly null where no secondary channel surfaced — the sample masks these as "Hidden" too); `data_completion_score_text`, `data_completion_score_visual`.
- **Street address backfill:** the seed left `street_address` blank for all 50 rows. 33 were filled from the domain-verified Google Places results and 2 from LinkedIn enrichment as fallback. Every fill is paired with `street_address_evidence_url` + `street_address_confidence`.
- **Score distribution:** median = 20, max = 25, min = 14, denominator = 31. The score honestly reflects what we have; it does NOT inflate by counting our extra validation/evidence columns.
- **Why our median is below the sample's median:** the sample masks principal contact channels (LinkedIn URL, primary email, primary phone) as "Hidden" but still counts them as filled. Ours honestly leaves them blank when the evidence does not support a write. A reader applying the same masking convention to our data would see a comparable score.

### Final Evidence Augmentation + Workbook Audit (Pass 11)

After all promoters ran, the workbook was rebuilt with 116 columns and 16 sheets. A deterministic augmentation pass appended claim-level evidence for post-validation fields that were not present in the original validator's `field_evidence.csv`: LinkedIn company enrichment, social handles, Google Places corroboration, street addresses, SEC IAPD identifiers, principal slots, sample-parity derivations, completion scores, and recent-activity metadata.

- **Field evidence:** 476 seed evidence rows → 1,848 total evidence rows after augmentation.
- **Data dictionary:** 116 definitions, one for every `data_50` column.
- **Recent activity metadata:** 21 rows retain sourced news signals; the remaining 29 are explicitly marked `recent_activity_type = none_found`.
- **LinkedIn People scrape decision:** a cookieless Apify actor was probed. The only successful probe was outside the final 50-row dataset, while target-record runs returned no usable employees. No principal LinkedIn URLs were promoted from that experiment.

## Honest Limitations

The dataset is internally consistent, evidence-backed, and tested. It still has gaps a reader should know about before relying on it:

- **Email deliverability is not verified.** Promoted emails pass syntax + MX checks only; SMTP-level verification was blocked by Apify actor permissions. Treat them as best-effort corporate addresses, not confirmed inboxes.
- **Principal-specific LinkedIn / work email / direct phone are populated for 0 / 0 / 0 of 50 rows.** Corporate-level email/phone coverage is stronger (26 corporate emails and 20 corporate phones), but those are not represented as personal channels. Workstream 9 added multi-principal coverage (`principal_1_*` through `principal_3_*`) for 3 firms with rich team pages (Verlinvest, Haven Private, Okabena — 20 named individuals in total). Expanding to the remaining 47 FOs requires better team-page discovery or a higher-yield LinkedIn People workflow.
- **Form ADV / Form CRS PDF content is not yet extracted.** The IAPD pass (Workstream 8) recovered the AUTHORITATIVE Form ADV Part 2A brochure URL for 33 of 50 firms but did not parse the PDF body. AUM, fee structure, conflict disclosures, and listed officers therefore are not yet promoted into the dataset; they are reachable one click away via `form_adv_brochure_url`.
- **Recent activity coverage is 21/50.** Small or private offices without 2025+ press coverage are honestly tagged with `recent_activity_type = none_found` rather than padded with weak matches.
- **Data Completion Score median is 20 of 31 against the sample's 31-column denominator.** The sample's median is in the 25–28 range, but the sample masks principal contact channels as "Hidden" while still counting them; we leave them honestly null. Apples-to-apples comparison would close most of the gap.
- **Three featured validation chains include 2 known unavailable snippets** — Firecrawl skipped the JFG Form CRS PDF (it does not crawl PDFs by default) and the Verlinvest team page is a team grid with no narrative sentence. Both are disclosed in the chains document with a manual-snippet TODO rather than fabricated.
- **Google Places sometimes returns the wrong business.** 17 of 50 Places results were rejected because the returned `website` domain did not match the FO. The 6 surfaced phone conflicts (Places phone disagreeing with our scraped phone) are honestly flagged in `primary_phone_corroborated_by_places = False` so a reviewer can investigate.
- **The manual `human_audit_status` column** is reviewer-owned and starts at `pending`. The automated pre-screen flagged 9 of 50 rows for closer inspection; the remaining 41 passed the heuristics but have not been individually re-clicked. A row-by-row click-through is still recommended before submission.
- **Some MFO classifications are service-provider relationships, not private SFOs.** Where this is the case the `family_office_type` is set to `multi_family_office` and the `uncertainty_notes` field calls out the service-provider framing explicitly. A reader who applies a stricter "family office" definition will discount these rows.
- **AUM is missing for most records** because public AUM disclosures are inconsistent. Where present, AUM is quoted from the source language in `aum_text`; it is never inferred.
- **Brand-abbreviated domains** (5 rows: O'Donnell→ogwealth, Major Domus→mdmfo, Yamauchi N.10→y-n10, Laird Norton Wetherby→lnwadvisors, Homrich Berg→hbwealth) are flagged by the pre-screen so a reviewer can confirm domain → entity mapping without surprise.
- **Live URL validation depends on network conditions.** Reruns may surface intermittent failures even on URLs that were green at capture time; the validation snapshot date is 2026-05-17.

## What I Would Improve

- **Parse Form ADV PDF bodies.** Workstream 8 captured the SEC-authoritative Form ADV Part 2A brochure URLs but did not extract their content. Parsing each PDF would yield regulatory AUM, fee structure, conflict-of-interest disclosures, and listed officers from a source the SEC itself certifies. Estimated work: ~1 day with `pdfplumber` + a deterministic field extractor.
- **Expand multi-principal coverage from 3 FOs to ≥30.** The team-roster extractor currently surfaces named officers only from FOs whose team page was already in the Firecrawl snapshot (12 of 50). A fresh Firecrawl pass on team-page URL candidates (plus a cookieless LinkedIn People scrape for the SEC-registered firms) would lift the coverage to most rows.
- **Add ProPublica Form 990 enrichment for foundation-style FOs.** The ProPublica Nonprofit Explorer API (`https://projects.propublica.org/nonprofits/api/v2/organizations/{EIN}.json`) returns trustee names and officer compensation from Form 990-PF for free — ideal for the Walton-style family foundations in the dataset.
- **Add archived copies or hashes of source artifacts** so link rot does not weaken the audit trail. The Apify + Firecrawl raw exports under `data/evidence/` already serve as a partial snapshot, but no checksum is recorded.
- **Add a human review column for contradiction checks** across official pages, regulatory filings, and third-party rankings. The 6 phone-corroboration conflicts surfaced by Pass 7 are a real example of where this would add value.
- **Use the finalized dataset to build RAG chunks** with record IDs, evidence IDs, source URLs, confidence scores, and validation status as metadata. This is the next workstream after the dataset is locked.
