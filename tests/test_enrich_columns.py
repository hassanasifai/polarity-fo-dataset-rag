from __future__ import annotations

from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from fo_dataset_pipeline.enrich_columns import (
    NEW_COLUMNS,
    app,
    derive_domain,
    derive_url_quality,
    enrich_dataframe,
    load_email_evidence_lookup,
)


def test_derive_domain_strips_www_and_scheme() -> None:
    assert derive_domain("https://www.cattrail.com/") == "cattrail.com"
    assert derive_domain("https://atcapital.com.sg/about") == "atcapital.com.sg"
    assert derive_domain("") == ""


def test_derive_url_quality_categorizes_status_codes() -> None:
    assert derive_url_quality(True, 200) == "Highest"
    assert derive_url_quality(True, 204) == "High"
    assert derive_url_quality(True, 301) == "Medium"
    assert derive_url_quality(True, 404) == "Low"
    assert derive_url_quality(False, 200) == "Failed"
    assert derive_url_quality(True, "") == "Unknown"
    assert derive_url_quality(True, "not-a-number") == "Unknown"


def test_load_email_evidence_lookup_keys_by_lowercased_email(tmp_path: Path) -> None:
    csv = tmp_path / "ev.csv"
    pd.DataFrame(
        [
            {"email": "Info@Foo.com", "validation_code": "mx_ok",
             "validation_explanation": "good", "email_quality_assessment": "good_public_domain_mx"},
        ]
    ).to_csv(csv, index=False)
    lookup = load_email_evidence_lookup(csv)
    assert "info@foo.com" in lookup
    assert lookup["info@foo.com"]["primary_email_validation_code"] == "mx_ok"


def test_load_email_evidence_lookup_empty_when_file_missing(tmp_path: Path) -> None:
    assert load_email_evidence_lookup(tmp_path / "missing.csv") == {}


def test_enrich_dataframe_adds_all_new_columns() -> None:
    df = pd.DataFrame(
        [
            {"website_url": "https://www.foo.com/", "website_ok": True,
             "website_status_code": 200, "primary_email": "info@foo.com"},
        ]
    ).fillna("")
    lookup = {"info@foo.com": {
        "primary_email_validation_code": "mx_ok",
        "primary_email_code_explanation": "good",
        "primary_email_quality_assessment": "good_public_domain_mx",
    }}
    enriched = enrich_dataframe(df, lookup, validation_period="2026-05")
    for column in NEW_COLUMNS:
        assert column in enriched.columns
    assert enriched.loc[0, "data_validation_period"] == "2026-05"
    assert enriched.loc[0, "family_office_domain"] == "foo.com"
    assert enriched.loc[0, "url_quality"] == "Highest"
    assert enriched.loc[0, "primary_email_validation_code"] == "mx_ok"


def test_enrich_dataframe_leaves_email_columns_blank_when_no_email() -> None:
    df = pd.DataFrame(
        [{"website_url": "https://foo.com/", "website_ok": True,
          "website_status_code": 200, "primary_email": ""}]
    ).fillna("")
    enriched = enrich_dataframe(df, {}, validation_period="2026-05")
    assert enriched.loc[0, "primary_email_validation_code"] == ""
    assert enriched.loc[0, "primary_email_quality_assessment"] == ""


def test_cli_run_enrich_persists_changes(tmp_path: Path) -> None:
    dataset = tmp_path / "validated.csv"
    pd.DataFrame(
        [{"record_id": "fo_001", "website_url": "https://foo.com/",
          "website_ok": True, "website_status_code": 200, "primary_email": ""}]
    ).to_csv(dataset, index=False)
    evidence = tmp_path / "ev.csv"
    pd.DataFrame(
        [
            {
                "email": "info@foo.com",
                "validation_code": "mx_ok",
                "validation_explanation": "good",
                "email_quality_assessment": "good_public_domain_mx",
            }
        ]
    ).to_csv(evidence, index=False)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["--dataset", str(dataset), "--email-evidence", str(evidence)],
    )
    assert result.exit_code == 0, result.output
    df = pd.read_csv(dataset)
    assert df.loc[0, "family_office_domain"] == "foo.com"
    assert df.loc[0, "data_validation_period"] == "2026-05"
