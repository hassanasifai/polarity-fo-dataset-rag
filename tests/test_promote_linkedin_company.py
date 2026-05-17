from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from fo_dataset_pipeline.promote_linkedin_company import (
    CONFIDENCE_VALUE,
    EVIDENCE_COLUMN,
    PROMOTED_COLUMNS,
    PROMOTED_VALUE_COLUMNS,
    _domain,
    _format_headquarters,
    _format_int,
    _format_specialties,
    app,
    load_linkedin_lookup,
    promote_row,
)


def test_format_specialties_parses_python_list_literal() -> None:
    raw = "['Family Office Services', 'Tax Planning', 'ESG Investing']"
    assert _format_specialties(raw) == "Family Office Services; Tax Planning; ESG Investing"


def test_format_specialties_handles_plain_string() -> None:
    assert _format_specialties("Wealth Management") == "Wealth Management"


def test_format_specialties_handles_empty_and_nan() -> None:
    assert _format_specialties("") == ""
    assert _format_specialties(None) == ""
    assert _format_specialties(pd.NA) == ""


def test_format_int_strips_decimal_from_float_string() -> None:
    assert _format_int("843.0") == "843"
    assert _format_int(17250.0) == "17250"


def test_format_int_returns_empty_for_nan() -> None:
    assert _format_int(None) == ""
    assert _format_int(pd.NA) == ""


def test_format_headquarters_joins_present_parts_only() -> None:
    row = {"street": "10 Sterling Blvd", "city": "Englewood", "state": "New Jersey",
           "country": "US", "postalCode": "07631"}
    assert _format_headquarters(row) == "10 Sterling Blvd, Englewood, New Jersey, US, 07631"


def test_format_headquarters_skips_nan_parts() -> None:
    row = {"street": "10 Main St", "city": "", "state": pd.NA,
           "country": "US", "postalCode": None}
    assert _format_headquarters(row) == "10 Main St, US"


def test_domain_strips_scheme_and_www() -> None:
    assert _domain("https://www.cattrail.com/") == "cattrail.com"
    assert _domain("http://foo.com") == "foo.com"
    assert _domain("bar.io") == "bar.io"
    assert _domain("") == ""
    assert _domain(None) == ""


def test_load_linkedin_lookup_keeps_only_company_urls(tmp_path: Path) -> None:
    csv = tmp_path / "li.csv"
    pd.DataFrame(
        [
            {"website": "http://foo.com", "linkedinUrl": "https://linkedin.com/company/foo"},
            {"website": "http://bar.com", "linkedinUrl": "https://linkedin.com/in/someone"},
            {"website": "http://baz.com", "linkedinUrl": ""},
            {"website": "http://qux.com",
             "linkedinUrl": "https://linkedin.com/school/qux-university"},
        ]
    ).to_csv(csv, index=False)
    lookup = load_linkedin_lookup(csv)
    assert set(lookup.keys()) == {"foo.com"}


def test_promote_row_returns_empty_when_no_linkedin_row() -> None:
    record = {"website_url": "https://acme.com"}
    assert promote_row(record, None) == {}


def test_promote_row_refuses_domain_mismatch() -> None:
    record = {"website_url": "https://acme.com"}
    linkedin_row = {
        "website": "https://different.com",
        "linkedinUrl": "https://linkedin.com/company/acme",
        "employeeCount": 100.0,
    }
    assert promote_row(record, linkedin_row) == {}


def test_promote_row_refuses_personal_linkedin_url() -> None:
    record = {"website_url": "https://acme.com"}
    linkedin_row = {
        "website": "https://acme.com",
        "linkedinUrl": "https://linkedin.com/in/somebody",
        "employeeCount": 50.0,
    }
    assert promote_row(record, linkedin_row) == {}


def test_promote_row_promotes_all_available_fields() -> None:
    record = {"website_url": "https://acme.com"}
    linkedin_row = {
        "website": "https://acme.com",
        "linkedinUrl": "https://linkedin.com/company/acme",
        "employeeCount": 843.0,
        "followerCount": 17250.0,
        "specialties": "['Family Office Services', 'Tax Planning']",
        "companySize": "501-1,000 employees",
        "industry": "Financial Services",
        "foundedYear": 2004.0,
        "street": "10 Main St",
        "city": "Englewood",
        "state": "New Jersey",
        "country": "US",
        "postalCode": "07631",
    }
    updates = promote_row(record, linkedin_row)
    assert updates["linkedin_employee_count"] == "843"
    assert updates["linkedin_follower_count"] == "17250"
    assert updates["linkedin_specialties"] == "Family Office Services; Tax Planning"
    assert updates["linkedin_company_size_band"] == "501-1,000 employees"
    assert updates["linkedin_industry"] == "Financial Services"
    assert updates["linkedin_founded_year"] == "2004"
    assert updates["linkedin_headquarters_full"] == \
        "10 Main St, Englewood, New Jersey, US, 07631"
    assert updates[EVIDENCE_COLUMN] == "https://linkedin.com/company/acme"
    assert updates["linkedin_company_confidence"] == CONFIDENCE_VALUE


def test_promote_row_does_not_overwrite_existing_values() -> None:
    record = {
        "website_url": "https://acme.com",
        "linkedin_employee_count": "100",  # existing value
        "linkedin_industry": "Existing Industry",
    }
    linkedin_row = {
        "website": "https://acme.com",
        "linkedinUrl": "https://linkedin.com/company/acme",
        "employeeCount": 843.0,
        "industry": "New Industry",
        "foundedYear": 2004.0,
    }
    updates = promote_row(record, linkedin_row)
    assert "linkedin_employee_count" not in updates
    assert "linkedin_industry" not in updates
    assert updates["linkedin_founded_year"] == "2004"


def test_promote_row_returns_empty_when_all_fields_empty() -> None:
    record = {"website_url": "https://acme.com"}
    linkedin_row = {
        "website": "https://acme.com",
        "linkedinUrl": "https://linkedin.com/company/acme",
        # all enrichment fields blank
    }
    assert promote_row(record, linkedin_row) == {}


def test_run_promotion_writes_csv_and_json(tmp_path: Path) -> None:
    dataset = tmp_path / "validated.csv"
    pd.DataFrame(
        [
            {
                "record_id": "fo_001",
                "family_office_name": "Acme",
                "website_url": "https://acme.com",
            },
        ]
    ).to_csv(dataset, index=False)
    linkedin_csv = tmp_path / "li.csv"
    pd.DataFrame(
        [
            {
                "website": "https://acme.com",
                "linkedinUrl": "https://linkedin.com/company/acme",
                "employeeCount": 50.0,
                "followerCount": 1200.0,
                "specialties": "['Family Office']",
                "companySize": "11-50 employees",
                "industry": "Financial Services",
                "foundedYear": 2010.0,
                "street": "1 Main",
                "city": "NYC",
                "state": "NY",
                "country": "US",
                "postalCode": "10001",
            }
        ]
    ).to_csv(linkedin_csv, index=False)
    json_output = tmp_path / "out.json"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--dataset", str(dataset),
            "--linkedin-evidence", str(linkedin_csv),
            "--json-output", str(json_output),
        ],
    )
    assert result.exit_code == 0, result.output

    df = pd.read_csv(dataset)
    assert df.loc[0, "linkedin_employee_count"] == 50
    assert df.loc[0, "linkedin_founded_year"] == 2010
    assert df.loc[0, "linkedin_industry"] == "Financial Services"
    assert df.loc[0, EVIDENCE_COLUMN] == "https://linkedin.com/company/acme"
    for column in PROMOTED_COLUMNS:
        assert column in df.columns
    rows = json.loads(json_output.read_text(encoding="utf-8"))
    assert rows[0]["linkedin_industry"] == "Financial Services"
    assert "linkedin_employee_count" in PROMOTED_VALUE_COLUMNS


def test_run_promotion_no_match_yields_empty_columns(tmp_path: Path) -> None:
    dataset = tmp_path / "validated.csv"
    pd.DataFrame(
        [
            {
                "record_id": "fo_001",
                "family_office_name": "Acme",
                "website_url": "https://acme.com",
            },
        ]
    ).to_csv(dataset, index=False)
    linkedin_csv = tmp_path / "li.csv"
    pd.DataFrame(
        [
            {
                "website": "https://different.com",
                "linkedinUrl": "https://linkedin.com/company/different",
                "employeeCount": 100.0,
            }
        ]
    ).to_csv(linkedin_csv, index=False)
    json_output = tmp_path / "out.json"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--dataset", str(dataset),
            "--linkedin-evidence", str(linkedin_csv),
            "--json-output", str(json_output),
        ],
    )
    assert result.exit_code == 0, result.output
    df = pd.read_csv(dataset)
    for column in PROMOTED_COLUMNS:
        assert column in df.columns
        # Column exists but is blank for the unmatched row.
        value = df.loc[0, column]
        assert pd.isna(value) or value == ""
    assert json_output.exists()
