# Methodology Summary Template

## Observed

- Assessment requires 50 original, validated family office records.
- The provided sample workbook is a schema reference only; rows must not be copied.
- Evaluation emphasizes visible reasoning, uncertainty, and validation.

## Assumptions

| Assumption | Confidence | How to Verify |
|---|---:|---|
| A record can be accepted when family-office relevance is supported by at least two source URLs. | Medium | Compare against evaluator feedback and strengthen with regulatory or official evidence. |
| Publicly available contact data is acceptable only when published by the person, company, filing, or credible directory. | High | Review source terms and avoid inferred/private contact data. |
| Multi-family offices and family-backed investment firms can be included if labeled clearly. | Medium | Keep `family_office_type` explicit and provide uncertainty notes. |

## Discovery Process

1. Build a candidate list from official company sites, family-office service pages, credible investment firm profiles, SEC ADV pages where available, LinkedIn company pages, and recent news.
2. Reject candidates when the source only implies wealth management without a family office, family-backed capital, or ultra-high-net-worth family service angle.
3. Prefer original official-source evidence over copied directory rows.

## Enrichment Process

- Entity profile: official website, entity type, city, country, LinkedIn, description.
- Investment intelligence: thesis, sectors, mandates, AUM where public.
- Principal/contact intelligence: only public decision-maker names, titles, LinkedIn, and contact details.
- Recent signals: investments, commitments, hiring, filings, news, or portfolio updates.

## Validation Logic

- Schema validation: required identity and evidence fields parse correctly.
- Evidence validation: at least two source URLs per accepted record.
- URL validation: website and sources are checked with live HTTP requests.
- Confidence scoring: completeness + evidence quality + reachable sources + FO classification clarity.
- Manual review: low-confidence or ambiguous records remain in `needs_review`.

## Improvements

- Add SEC ADV lookup for registered investment advisers.
- Add OpenCorporates or jurisdiction registry checks for legal names.
- Add source snapshots for reproducibility.
- Add Great Expectations after the 50-row dataset is complete.
- Add RAG ingestion once the accepted dataset is stable.
