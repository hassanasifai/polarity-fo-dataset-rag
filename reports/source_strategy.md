# Source Strategy and Rejection Logic

## Observed

- The assessment rewards visible validation, not just a polished spreadsheet.
- Directory-backed rows are fragile because they can make an inferred family-office
  classification look like a verified fact.
- True single-family offices are often private, so the defensible public dataset should
  clearly separate single-family offices, multi-family offices, and family-office service
  providers.

## Source Hierarchy

1. Primary official evidence: official entity website, official family office page,
   official investment office page, official disclosure brochure, or official annual
   report.
2. Regulatory or registry corroboration: SEC IAPD/Form ADV, Companies House, FCA,
   government registry, or equivalent jurisdictional record.
3. Official press release: company-hosted or wire-distributed release for launch,
   strategy, team, or asset/service disclosure.
4. Secondary reputable evidence: business press or institutional database used only as
   support.
5. Discovery-only evidence: SWFI, lead-gen databases, LinkedIn-only profiles, scraped
   lists, and unsourced rankings.

## Acceptance Gates

- `family_office_type` must be explicit and cannot silently convert a service provider
  or holding company into a classic single-family office.
- Accepted rows require a live website and at least two live source URLs.
- SWFI-style discovery directory links are blocked from final acceptance.
- Placeholder values such as `Hidden`, `TBD`, `dummy`, and `example.com` are rejected.
- The raw seed is compared with the provided sample workbook to avoid copied records.
- SEC IAPD/Form ADV values are promoted only from the SEC public API and are kept
  separate from web-derived summaries.
- Google Places is corroboration only. A Places row is accepted only when the returned
  website domain matches the FO domain; mismatched results are rejected.
- LinkedIn company enrichment is accepted only when the LinkedIn company-page `website`
  field shares the FO website domain. Personal profiles are not used as company evidence.
- Principal slots are promoted only from official team/about/leadership pages. Personal
  LinkedIn, email, and direct-phone fields stay blank unless directly observed.
- Every post-validation promoted value must have a paired evidence URL/confidence value
  and an augmented row in `field_evidence.csv`.

## Replaced or Downgraded Rows

- Removed/replaced broad foundation, royal estate, and institutional asset-manager rows
  where family-office status depended too heavily on SWFI or inference.
- Replaced them with official-source-backed family offices or multi-family offices such
  as Cat Trail Capital, Ralph Family Office, Ohana Advisors, Longwall Family Office,
  CM Wealth, JFG Family Office, Scott Capital Partners, Persimmon Capital Management,
  and Third View Private Wealth.

## Remaining Risk

- Some records are multi-family offices or family-office service providers rather than
  pure single-family offices. This is preserved in `family_office_type` and
  `uncertainty_notes`.
- Claim-level evidence is now comprehensive for promoted fields, but many snippets are
  concise provenance statements rather than manually selected verbatim source quotes.
  The three featured validation chains retain exact quote-level support.
- The LinkedIn People scrape was tested but not promoted because target-record runs
  returned no usable employee records. Principal fields stay sourced from official
  team/about/profile pages.
- Form ADV brochure URLs are captured for SEC-registered firms. PDF text is parsed
  conservatively for regulatory AUM and fee labels when the pattern is reliable; officer
  table extraction remains manual-review only.
