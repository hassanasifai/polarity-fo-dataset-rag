# Dataset Phase Design Note

## Current Status

- Raw seed file contains exactly 50 original records.
- Final generated CSV/XLSX/JSON contains 50 accepted records.
- Confidence distribution is 50 high, 0 medium, 0 low.
- Sample workbook overlap is checked and currently returns no overlaps.
- Final source URLs contain zero SWFI links.
- Final workbook includes source registry and field-evidence tabs.
- RAG implementation is intentionally deferred until this dataset phase remains stable.

## ASCII Flow

```text
Candidate discovery
  -> raw CSV with source links
  -> schema validation
  -> URL/domain validation
  -> confidence scoring
  -> accepted / needs_review split
  -> CSV + XLSX + methodology + validation chains
```

## Schema Groups

- Entity identity: name, type, website, LinkedIn, address, country.
- Investment intelligence: description, thesis, sectors, AUM text, recent activity.
- Principal intelligence: principal name, title, LinkedIn, public email, public phone.
- Evidence: source URLs, source notes, extraction method, evidence quality, uncertainty notes.
- Validation: URL status, source count, confidence, score, status, validation notes.

## Great Expectations Mapping

- `expect_column_to_exist`: all required schema fields.
- `expect_column_values_to_not_be_null`: name, type, description, website, country, sources.
- `expect_column_values_to_match_regex`: website/source URLs, email, phone when present.
- `expect_table_row_count_to_be_between`: exactly 50 for final delivery.
- `expect_column_values_to_be_between`: validation score 0-100.

## Failure Handling

- Schema parse failure: stop the run and report row-level errors.
- Weak evidence: keep row, mark `needs_review`, lower confidence.
- Sample-workbook overlap: stop the run before live validation.
- Discovery-only directory evidence in final `source_urls`: mark row `needs_review`.
- Fewer than two reachable source URLs: mark row `needs_review`.
- Unreachable official website: mark row `needs_review`.
- Final count mismatch: write artifacts for inspection, then exit non-zero.
- URL failure: do not auto-delete; preserve for manual follow-up because some official sites block bots.
- Fewer than 50 accepted records: dataset is not submission-ready.

## Verification Commands

```powershell
cd D:\PolarityIQ_Workspace\fo_dataset_pipeline
python -m pytest -q
ruff check .
python -m fo_dataset_pipeline.cli --input data/raw/family_offices_seed.csv --required-count 50
```

## RAG Compatibility

Each final row can become a single document with structured metadata. Later chunking should preserve
the table row as one unit and attach source URLs, confidence, and validation status as metadata.
