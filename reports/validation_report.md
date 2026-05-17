# Validation Report

## Observed
- Input records processed: 50
- Accepted records: 50
- Needs review: 0
- Confidence distribution: high=50, medium=0, low=0

## Validation Rules
- Required identity fields must parse through the Pydantic schema.
- Accepted records require score >= 80, a reachable website, and at least two reachable source URLs.
- SWFI-style discovery directory links are blocked from final acceptance.
- Website and source URLs are checked with live HTTP requests.
- Confidence is derived from source sufficiency, website reachability, evidence quality, and data completeness.

## Records Needing Review
- None
