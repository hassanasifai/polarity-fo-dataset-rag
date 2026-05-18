# Apify Evidence Workflow

## Purpose

Apify is used as an evidence-capture layer, not as the authority deciding which records
belong in the final dataset.

## Actors Used

- `apify/google-search-scraper`: discovery only.
- `apify/website-content-crawler`: exact-source evidence capture.

## Full Actor Stack for the Next Collection Pass

The current verified dataset used Apify as a limited evidence-capture layer. For a
larger replacement/enrichment pass, use the expanded actor stack in
`docs/apify_actor_stack_full.csv`:

- Discovery: `apify/google-search-scraper`
- Official website capture: `apify/website-content-crawler`
- Structured extraction: `apify/cheerio-scraper`, then `apify/playwright-scraper`
  only when static extraction is incomplete.
- Address and phone corroboration: `compass/crawler-google-places`
- Public contact extraction: `vdrmota/contact-info-scraper`
- Contact deduplication: `lukaskrivka/contact-details-merge-deduplicate`
- LinkedIn company enrichment: `automation-lab/linkedin-company-scraper`
- Public profile enrichment: `thirdwatch/linkedin-profile-scraper`
- Recent activity signals: `scrapeio/google-news-scraper`
- Email deliverability validation: `account56/email-verifier`
- Optional licensed investment enrichment:
  `automation-lab/crunchbase-scraper`
- Optional secondary firmographics:
  `vivid_astronaut/company-enrichment`
- Fallback custom extraction: `apify/web-scraper`
- Authoritative US regulatory validation:
  private custom actor or direct Python module for SEC IAPD, Form ADV, EDGAR,
  and 13F checks.

Column-level mapping is maintained in `docs/apify_column_mapping_full.csv`.
Discovery seed targets that avoid the sample workbook are maintained in
`data/evidence/apify_inputs/family_office_discovery_seed_targets.csv`.

Apify outputs remain raw collection and enrichment signals. A row is not
accepted until entity identity, official website/domain, location, and at least
one investment or mandate signal are source-backed and scored by the validator.

## Runs Completed

See `docs/apify_run_log.csv` for run IDs, status, item count, and estimated cost.

Completed runs:

- `evidence_smoke_10`: depth-0 crawl of 10 exact evidence URLs.
- `evidence_exact_sources_full`: depth-0 crawl of all non-PDF final source URLs.
- `us_discovery_family_office_01`: narrow US discovery SERP run.
- `evidence_exact_sources_full_2026_05_17`: refreshed exact-source crawl.
- `us_discovery_family_office_2026_05_17`: refreshed US discovery search.
- `global_discovery_family_office_2026_05_17`: refreshed global discovery search.
- `contact_info_official_websites_2026_05_17`: public contact extraction from
  official websites only.
- `google_news_recent_signals_2026_05_17`: recent news signals for the 50 final
  records.
- `google_places_address_validation_2026_05_17`: capped Google Places
  corroboration for address/phone signals.
- `linkedin_company_enrichment_2026_05_17`: LinkedIn company enrichment on
  company links found during the contact crawl.
- `playwright_homepage_fallback_2026_05_17`: dynamic homepage extraction
  fallback for final-record official websites.

The `account56/email-verifier` actor returned a full-permission approval
requirement for the current Apify account. The run log records this as blocked,
and `email_validation_evidence.csv` contains a local syntax/MX fallback instead
of deliverability verification.

The `apify/cheerio-scraper` actor also returned the same full-permission approval
requirement for the current Apify account, so `cheerio_homepage_evidence.csv`
records the blocked state and `apify/playwright-scraper` serves as the fallback
dynamic extraction evidence.

## Controls

- The API token is read from `APIFY_TOKEN`; it is not stored in source files.
- Crawls are depth 0 against exact source URLs for final evidence capture.
- Media is blocked and robots.txt is respected.
- PDFs are excluded from `website-content-crawler`; they remain in `source_registry.csv`
  and are marked as PDF-excluded in `apify_crawl_evidence.csv`.
- SERP output is flattened into `data/evidence/candidates_raw_from_apify.csv` and
  triaged as discovery evidence only.

## Outputs

- Raw actor outputs:
  `data/evidence/raw_apify_exports/2026-05-16/*.json`
- Raw actor CSV exports:
  `data/evidence/raw_apify_exports/2026-05-16/*.csv`
- Run log:
  `docs/apify_run_log.csv`
- Flattened discovery leads:
  `data/evidence/candidates_raw_from_apify.csv`
- Crawled evidence snippets:
  `data/processed/apify_crawl_evidence.csv`

## Validation Result

- Full exact-source crawl returned 98 crawled pages.
- `apify_crawl_evidence.csv` contains the original 112 row-level source crawls. The broader `source_registry.csv` now contains 338 source-reference rows after evidence backfill.
- 101 rows matched crawled markdown by canonical URL.
- 8 unmatched rows were PDFs intentionally excluded from website crawling.
- 3 unmatched rows were Baltisse pages that passed live HTTP checks but did not return
  Apify crawl items.

## Limitation

The Apify crawl provides page-level text snapshots. The final human validation step should
still select exact excerpts for the most important fields, especially AUM, principal
identity, family-office classification, and recent activity.
