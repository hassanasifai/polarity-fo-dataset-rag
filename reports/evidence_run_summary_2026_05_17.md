# Evidence Run Summary - 2026-05-17

## Objective

Refresh and expand the evidence layer for the 50-record family office dataset using
Apify and Firecrawl without treating raw scraper output as final truth.

## Runs Completed

| Layer | Tool / Actor | Output |
|---|---|---|
| Exact source snapshots | `apify/website-content-crawler` | 100 crawled items; `apify_crawl_evidence.csv` has 112 source rows and 103 matched crawl rows |
| Independent source snapshots | Firecrawl batch scrape | 101 scraped pages; `firecrawl_crawl_evidence.csv` has 112 source rows and 101 matched rows |
| Discovery candidates | `apify/google-search-scraper` | US and global discovery runs; 120 SERP rows flattened across two CSVs |
| Public contact extraction | `vdrmota/contact-info-scraper` | 50 official websites processed; 31 rows with emails and 20 rows with phones |
| Email validation | `account56/email-verifier` | Blocked by Apify full-permission approval requirement; local syntax/MX fallback generated for 53 public emails |
| Recent signals | `scrapeio/google-news-scraper` | 203 raw news signal rows across the 50 final records |
| Address/phone corroboration | `compass/crawler-google-places` | 50 capped Google Places rows |
| LinkedIn company enrichment | `automation-lab/linkedin-company-scraper` | 37 company enrichment rows from public LinkedIn links found during contact crawl |
| Static extraction fallback | `apify/cheerio-scraper` | Blocked by Apify full-permission approval requirement; limitation recorded |
| Dynamic extraction fallback | `apify/playwright-scraper` | 44 homepage extraction rows |

## Final Dataset Status

- Final dataset rows: 50
- Accepted rows after live validation: 50
- Workbook evidence tabs added:
  - `apify_evidence`
  - `firecrawl_evidence`
  - `contact_info_evidence`
  - `email_validation_evidence`
  - `google_news_signals`
  - `google_places_evidence`
  - `linkedin_company_evidence`
  - `cheerio_homepage`
  - `playwright_homepage`

## Important Caveats

- Firecrawl failed on two Venitage URLs with `SCRAPE_ALL_ENGINES_FAILED`; Apify and live
  HTTP validation still provide evidence for the record.
- PDFs were intentionally excluded from Firecrawl batch scraping to control credits.
- `account56/email-verifier` could not run until the Apify account approves the actor's
  full-permission request. The generated email validation sheet is a fallback syntax/MX
  check, not SMTP deliverability proof.
- `apify/cheerio-scraper` also requires full-permission approval for this Apify account.
  `apify/playwright-scraper` was run instead as the browser-based fallback.
- Google News, Google Places, LinkedIn enrichment, and contact extraction are evidence
  layers. They require source/name/domain review before any field is promoted into the
  final 50-record dataset.

## Verification

- `python -m fo_dataset_pipeline.cli --input data/raw/family_offices_seed.csv --required-count 50`
  passed with 50 accepted rows.
- `pytest tests/ -v --cov=. --cov-report=term-missing --cov-fail-under=80`
  passed with 23 tests and 81.09% coverage.
- `ruff check .` passed.
- `python -m pip_audit .` reported no known vulnerabilities for the local project.
