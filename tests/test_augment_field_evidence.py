from __future__ import annotations

from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from fo_dataset_pipeline.augment_field_evidence import (
    AUGMENTED_MARKER,
    app,
    build_augmented_rows,
)


def test_build_augmented_rows_adds_promoted_field_evidence() -> None:
    records = [
        {
            "record_id": "fo_001",
            "family_office_name": "Acme",
            "website_url": "https://acme.com",
            "validation_score": "94",
            "source_urls": "['https://acme.com/about']",
            "linkedin_employee_count": "50",
            "linkedin_company_evidence_url": "https://linkedin.com/company/acme",
            "linkedin_company_confidence": "linkedin_company_page",
            "sec_registered": "True",
            "sec_crd_number": "123",
            "sec_evidence_url": "https://adviserinfo.sec.gov/firm/summary/123",
            "sec_confidence": "sec_authoritative",
            "contact_full_name": "Jane Doe",
            "data_completion_score_text": "20",
            "recent_activity": "Acme hires CIO (Reuters, 2025-02-01) — https://r.com/a",
            "recent_activity_url": "https://r.com/a",
            "recent_activity_date": "2025-02-01",
            "recent_activity_outlet": "Reuters",
            "recent_activity_type": "news",
            "recent_activity_confidence": "name_token_date_filtered",
        }
    ]
    rows = build_augmented_rows(records)
    field_names = {row["field_name"] for row in rows}
    assert "linkedin_employee_count" in field_names
    assert "sec_crd_number" in field_names
    assert "contact_full_name" in field_names
    assert "data_completion_score_text" in field_names
    assert "recent_activity_url" in field_names
    assert all(AUGMENTED_MARKER in row["claim_id"] for row in rows)


def test_build_augmented_rows_documents_sec_no_match(tmp_path: Path) -> None:
    sec_dir = tmp_path / "sec"
    sec_dir.mkdir()
    records = [
        {
            "record_id": "fo_002",
            "website_url": "https://sfo.com",
            "validation_score": "88",
            "source_urls": "https://sfo.com",
            "sec_registered": "False",
        }
    ]
    rows = build_augmented_rows(records, sec_evidence_dir=sec_dir)
    assert rows[0]["field_name"] == "sec_registered"
    assert rows[0]["source_url"].endswith("fo_002.json")
    assert rows[0]["claim_type"] == "regulatory_registration_status"


def test_cli_replaces_prior_augmented_rows(tmp_path: Path) -> None:
    dataset = tmp_path / "data.csv"
    field_evidence = tmp_path / "field_evidence.csv"
    pd.DataFrame(
        [
            {
                "record_id": "fo_001",
                "website_url": "https://acme.com",
                "validation_score": "90",
                "source_urls": "https://acme.com",
                "primary_email": "info@acme.com",
                "primary_email_evidence_url": "https://acme.com",
                "primary_email_confidence": "corporate_public_listed",
            }
        ]
    ).to_csv(dataset, index=False)
    pd.DataFrame(
        [
            {"claim_id": "legacy", "record_id": "fo_001", "field_name": "name"},
            {
                "claim_id": f"fo_001{AUGMENTED_MARKER}primary_email",
                "record_id": "fo_001",
                "field_name": "primary_email",
            },
        ]
    ).to_csv(field_evidence, index=False)

    result = CliRunner().invoke(
        app,
        ["--dataset", str(dataset), "--field-evidence", str(field_evidence)],
    )
    assert result.exit_code == 0, result.output
    out = pd.read_csv(field_evidence)
    assert (out["claim_id"] == "legacy").sum() == 1
    assert (out["claim_id"] == f"fo_001{AUGMENTED_MARKER}primary_email").sum() == 1
