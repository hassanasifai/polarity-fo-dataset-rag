# Methodology Summary

## How I Worked This (HVL trace)

[OBSERVE] The reference workbook rewards entity, principal, contact, signal, and validation coverage, but the public family-office web is uneven: official sites often name the family or firm while hiding personal contact channels.

[ASSUME] [ASSUMPTION: a blank field is better than an inferred field when the evidence does not directly support the value.] I treated "Hidden" in the sample workbook as a masking convention, not permission to invent private data.

[QUESTION] The biggest judgment call was principal coverage. After the automated passes, only a few official team pages gave clean person-role pairs. I could have raised the completion score by pulling LinkedIn profiles from broad web search, but that would have mixed official evidence with name-matched guesses.

[HYPOTHESIS] The best submission signal is not maximum fill rate. It is a dataset where every filled value can survive a source click, and every blank value tells the evaluator what was searched and why it stayed blank.

[VALIDATE] I kept promotion gates deterministic: exact domain matches for LinkedIn company and Google Places, SEC/IAPD thresholded matches, date/name filters for recent activity, and quote-level validation chains. The workbook audit now checks row count, source count, evidence pairing, data dictionary coverage, and validation-chain quote extraction.

[CAVEATS] Two areas remain genuinely uncertain: Google Places phone conflicts, where the official/contact-source phone is retained as canonical; and personal principal profiles, where only official-profile LinkedIn URLs are promoted.

## How I Found Them

- Started with broad public discovery, then replaced directory-dependent rows with candidates supported by official websites, official family-office service pages, SEC/IAPD-style disclosures, company registry pages, or official PDFs.
- Excluded names copied from the provided sample workbook by comparing normalized entity names before export.
- Mixed single-family offices, multi-family offices, family-backed investment firms, and family-originated foundations only when the row label makes that classification explicit.

## How I Enriched Them

- Normalized entity type, headquarters location, principal or family context, investment thesis, sector focus, AUM text when public, source notes, and uncertainty notes.
- Left private contact fields blank unless the data was directly supportable from public business sources.
- Preserved source URLs on every row and generated a separate source registry plus field-evidence table so reviewers can trace each promoted value back to cited evidence.

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

Before contact promotion, each row was passed through a deterministic heuristic pre-screen (`audit_prescreen.py`). The pre-screen attaches an advisory `auto_prescreen_flag` (`look_carefully` or `looks_clean`) and a `;`-joined `auto_prescreen_reason`. The human-owned `human_audit_status` column carries the reviewer verdict.

- 9 of 50 rows were flagged `look_carefully` (5 service-provider MFOs already labeled explicitly + 5 rows whose website domain is a brand abbreviation of the legal name).
- 41 of 50 rows passed the pre-screen cleanly.
- Pre-screen is advisory only — it raises attention, not verdicts.

### Human Audit Application (Pass 1 verdicts)

Each flagged row was reviewed against the on-disk source notes, Firecrawl markdown snapshots, and Apify evidence before a verdict was applied. The decisions are checked into source in `apply_audit.py::AUDIT_DECISIONS` with a per-record rationale comment, so the audit trail is reproducible and inspectable.

- All 9 pre-screen-flagged rows received verdict `pass` — every classification is supported by the official site language already captured in the evidence sheets.
- 3 of those 9 (fo_011 O'Donnell→OG Wealth, fo_022 Major Domus→mdmfo, fo_026 Yamauchi No. 10→y-n10) received an additional `uncertainty_notes` line explicitly explaining the brand → domain abbreviation, so a reader of the dataset sees the domain mismatch acknowledged rather than hidden.
- The remaining 41 `looks_clean` rows were defaulted to `pass` without further notes.
- Final `human_audit_status` distribution: **`pass` = 50 / 50**.

## How I Validated Them

- Processed records: 50.
- Accepted records: 50.
- Row-level source links attached: 112.
- Source-registry rows after evidence backfill: 338.
- Confidence distribution: high=50, medium=0, low=0.
- Final source URLs no longer rely on SWFI-style discovery directories.
- Pydantic validation rejects missing required fields, invalid URLs, single-source rows, placeholder values, and malformed emails.
- Scoring rejects rows that lack a reachable official website or at least two reachable source URLs.
- The CLI checks candidate names against the assessment sample workbook and fails if any normalized name overlaps.
- The live validator requests the official website and every source URL and stores URL status metadata in the processed CSV, XLSX, and JSON outputs.
- Final delivery gate used `--required-count 50`, so the run fails unless exactly 50 records are accepted.

### Validation Decisions And Boundaries

- The Apify email-verifier actor was blocked by actor permissions, so I did not claim SMTP-level email verification. The new `primary_email_smtp_verified` field is `False` for every promoted corporate email.
- The LinkedIn People scraper experiment did not produce usable target-record employees. I promoted only official-site person-role evidence and official-profile LinkedIn links.
- Firecrawl skipped the JFG Form CRS PDF. I downloaded the public PDF and extracted the exact quote with `pypdf` rather than leaving a TODO or fabricating a snippet.
- The Verlinvest team page is a profile-card grid, not a narrative page. I used exact card text for names and roles and documented that judgment in the validation chain.
- Relaxing the recent-news filter would have increased coverage, but it pulled in low-signal round-ups and incidental mentions. I stopped at 21 sourced signals.

### Recent-Activity Promotion (Pass 4)

Recent activity was populated from `google_news_recent_signals.csv` (203 raw rows) using these filters in order: drop scraper-error rows, require `pubDate >= 2025-01-01`, require all informative tokens of the FO name to appear in the title, reject items from directory/aggregator sources (pitchbook, crunchbase, zoominfo, swfinstitute, wikipedia), then take the most recent surviving row.

- **Records with promoted `recent_activity`:** 21 of 50 (every entry: real headline + publication + date + article URL).
- **Records with explicit no-qualifying-news uncertainty note:** 29 of 50. These are predominantly smaller or private offices with no qualifying 2025+ signal in the 2026-05-17 news snapshot; leaving the field blank with a transparent note is the HVL-compliant choice over loose-matching.
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

- **Records matched (SEC-registered):** 37 of 50. Thirty-three passed the automated threshold and four near-threshold matches (Venitage, Okabena, AlTi, Greycourt) were accepted only after manual review against SEC aliases, CRD/file data, and location context. Each accepted match has a SEC-authoritative CRD number, SEC file number, registration status (ACTIVE/INACTIVE), the official firm name as filed, DBA aliases where available, branch count, registered address, and a direct link to the Form ADV Part 2A PDF brochure.
- **Records without an accepted SEC match:** 13 of 50. The `sec_registered = False` column and `uncertainty_notes` use snapshot-bound wording. They do not make a legal conclusion that the entity is exempt or permanently unregistered.
- **Per-row evidence files:** `data/evidence/sec_iapd_2026_05_17/{record_id}.json` carries the raw IAPD response, the queries tried, the match score, and the reasoning for both matched and unmatched rows.
- **What this adds:** authoritative regulatory identity for two-thirds of the dataset. Direct Form ADV PDF links unlock further evaluator drill-down (fee structure, conflict disclosures, investment strategy as filed). All data is sourced from the SEC's own public API — no third-party intermediary.

### Multi-Principal Intelligence (Pass 9, partial)

For the FOs whose Firecrawl-captured team/leadership/about pages contained named-person + role patterns, a deterministic markdown extractor surfaced 20 individuals across 3 firms (Verlinvest, Haven Private, Okabena Company). These are written into three principal slots per row (`principal_1_*` through `principal_3_*`), ordered by role seniority (Founder/Chair/President → CEO/CIO/CFO/COO → Managing Partner/Director → Partner → Principal → Director → Other), with every cell paired with the source page URL.

After the strict review, I added a narrow manual-review pass for the 3 featured validation-chain records. It fills official-site principal slots for Cat Trail, JFG, and Verlinvest. Only Verlinvest receives principal LinkedIn URLs because its official profile pages link to those personal profiles; Cat Trail and JFG keep LinkedIn slots blank.

- **Confidence label:** `corporate_team_page` — name and role observed on the FO's own team/about page.
- **What we refused to fabricate:** principal work emails and personal phones. Principal LinkedIn URLs are populated only when the entity's official profile/team page exposes the link.
- **Coverage limitation:** 5 of 50 FOs now have at least one multi-principal slot populated, and 1 of 50 has official personal LinkedIn profile URLs. Expanding coverage to ≥20 records would require a higher-yield LinkedIn People workflow or manual official-profile review across every firm; broad Google-to-LinkedIn name matching was rejected as too inferential for this submission.
- **Existing `principal_name` / `principal_title` columns** (populated for 19 of 50 from the original validator pass) are preserved unchanged; the new multi-principal columns are additive.

### Sample Workbook Parity + Data Completion Score (Pass 10)

The PolarityIQ-supplied sample workbook (`FO-MAX-data-sample-2.0.xlsx`) carries 31 columns and a Data Completion Score in the 19–29 range per row. To make our scoring directly comparable, our score counts populated cells across exactly those 31 sample columns (mapped to their snake_case equivalents in our workbook), NOT across our full 100+ column workbook. This is the same denominator the evaluator will diff against.

- **Sample-parity columns added:** `contact_first_name`, `contact_last_name`, `contact_full_name`, `contact_location` (derived from `principal_name` and HQ city/state/country); `contact_secondary_email`, `secondary_email_validation_code`, `email_code_explanation_secondary`, `email_quality_assessment_secondary`, `contact_secondary_phone` (left null where no secondary channel surfaced — the sample masks these as "Hidden" too); `data_completion_score_text`, `data_completion_score_visual`.
- **Street address backfill:** the seed left `street_address` blank for all 50 rows. 33 were filled from the domain-verified Google Places results and 2 from LinkedIn enrichment as fallback. Every fill is paired with `street_address_evidence_url` + `street_address_confidence`.
- **Score distribution:** median = 20, max = 25, min = 14, denominator = 31. The score reflects what we have; it does NOT inflate by counting our extra validation/evidence columns.
- **Why our median is below the sample's median:** the sample masks principal contact channels (LinkedIn URL, primary email, primary phone) as "Hidden" but still counts them as filled. Ours leaves them blank when the evidence does not support a write. A reader applying the same masking convention to our data would see a comparable score.

### Final Evidence Augmentation + Workbook Audit (Pass 11)

After all promoters ran, the workbook was rebuilt with 137 columns and 16 sheets. A deterministic augmentation pass appended claim-level evidence for post-validation fields that were not present in the original validator's `field_evidence.csv`: LinkedIn company enrichment, social handles, Google Places corroboration, street addresses, SEC IAPD identifiers, Form ADV parsed fields, principal slots, sample-parity derivations, completion scores, source-review fields, SEC near-match review fields, and recent-activity metadata.

- **Field evidence:** 476 seed evidence rows → 2,212 total evidence rows after augmentation.
- **Data dictionary:** 137 definitions, one for every `data_50` column.
- **Recent activity metadata:** 21 rows retain sourced news signals; the remaining 29 are explicitly marked `recent_activity_type = none_found`.
- **LinkedIn People scrape decision:** a cookieless Apify actor was probed. The only successful probe was outside the final 50-row dataset, while target-record runs returned no usable employees. No principal LinkedIn URLs were promoted from that experiment.

## Validation Boundaries

The dataset is internally consistent, evidence-backed, and tested. It still has gaps a reader should know about before relying on it:

- **Email deliverability is not verified.** Promoted emails pass syntax + MX checks only; SMTP-level verification was blocked by Apify actor permissions. Treat them as best-effort corporate addresses, not confirmed inboxes.
- **Principal-specific work email / direct phone are populated for 0 / 0 of 50 rows.** Corporate-level email/phone coverage is stronger (26 corporate emails and 20 corporate phones), but those are not represented as personal channels. Official-site principal slots are populated for the 3 featured validation records, and official personal LinkedIn URLs are populated only for Verlinvest's linked profile pages.
- **Form ADV PDF parsing is best-effort, not a legal-data parser.** The SEC PDFs were parsed for 37 registered firms and `sec_aum_usd` was populated for 36 records where the Item 5.F regulatory-AUM pattern was reliable. Fee labels are keyword-derived. Listed officers remain blank because the Schedule A table text was not reliable enough to promote without manual review.
- **Recent activity coverage is 21/50.** Small or private offices without 2025+ press coverage are tagged with `recent_activity_type = none_found` rather than padded with low-signal matches.
- **Data Completion Score median is 20 of 31 against the sample's 31-column denominator.** The sample's median is in the 25–28 range, but the sample masks principal contact channels as "Hidden" while still counting them; we leave them null unless evidence supports them. Apples-to-apples comparison would close most of the gap.
- **The three featured validation chains now have 18 extracted quote rows.** Two rows are manual-review extractions: the JFG PDF quote is extracted from downloaded PDF text, and the Verlinvest team quote is exact profile-card text from the Firecrawl markdown grid.
- **Google Places sometimes returns the wrong business.** 17 of 50 Places results were rejected because the returned `website` domain did not match the FO. The 6 surfaced phone conflicts (Places phone disagreeing with our scraped phone) are flagged in `primary_phone_corroborated_by_places = False` so a reviewer can investigate.
- **The final `human_audit_status` distribution is `pass=50/50`.** Nine flagged rows received explicit checked-in review decisions. The remaining 41 were accepted through deterministic evidence gates rather than a fresh live click-through on submission day.
- **Some MFO classifications are service-provider relationships, not private SFOs.** Where this is the case the `family_office_type` is set to `multi_family_office` and the `uncertainty_notes` field calls out the service-provider framing explicitly. A reader who applies a stricter "family office" definition will discount these rows.
- **Self-described AUM is still conservative.** SEC regulatory AUM is parsed for registered firms where the Form ADV text supports it, but marketing-site AUM remains blank unless the source says it directly.
- **Brand-abbreviated domains** (5 rows: O'Donnell→ogwealth, Major Domus→mdmfo, Yamauchi N.10→y-n10, Laird Norton Wetherby→lnwadvisors, Homrich Berg→hbwealth) are flagged by the pre-screen so a reviewer can confirm domain → entity mapping without surprise.
- **Live URL validation depends on network conditions.** Reruns may surface intermittent validation changes even on URLs that were green at capture time; the validation snapshot date is 2026-05-17.

## What I Would Improve

- **Improve Form ADV officer extraction.** Regulatory AUM now parses for 36 of the 37 SEC-registered records, but Schedule A officer tables still need a page-aware extractor plus manual validation before promotion.
- **Expand multi-principal coverage from 5 FOs to ≥30.** The team-roster extractor currently surfaces named officers only from FOs whose team page was already in the Firecrawl snapshot or manually reviewed for the featured chains. A fresh Firecrawl pass on team-page URL candidates would lift the coverage without relying on inferred LinkedIn matches.
- **Add ProPublica Form 990 enrichment for foundation-style FOs.** The ProPublica Nonprofit Explorer API (`https://projects.propublica.org/nonprofits/api/v2/organizations/{EIN}.json`) returns trustee names and officer compensation from Form 990-PF for free — ideal for the Walton-style family foundations in the dataset.
- **Add archived copies or hashes of source artifacts** so link rot does not reduce the audit trail. The Apify + Firecrawl raw exports under `data/evidence/` already serve as a partial snapshot, but no checksum is recorded.
- **Add a human review column for contradiction checks** across official pages, regulatory filings, and third-party rankings. The 6 phone-corroboration conflicts surfaced by Pass 7 are a real example of where this would add value.
- **Keep public artifacts and dataset exports in lockstep.** The evaluator CSV, processed CSV/JSON/XLSX, evidence sheets, and screen recording should all refer to the same 50-record snapshot.
