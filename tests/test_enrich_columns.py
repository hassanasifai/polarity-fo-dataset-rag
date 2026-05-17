from __future__ import annotations

from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from fo_dataset_pipeline.enrich_columns import (
    NEW_COLUMNS,
    SECONDARY_CONTACT_UNCERTAINTY_NOTE,
    app,
    derive_contact_location,
    derive_domain,
    derive_url_quality,
    enrich_dataframe,
    load_email_evidence_lookup,
    split_principal_name,
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


def test_split_principal_name_splits_first_and_last() -> None:
    assert split_principal_name("David Dekker") == ("David", "Dekker")
    assert split_principal_name("Russell W. Dekker") == ("Russell W.", "Dekker")
    assert split_principal_name("Marc Angle Jr.") == ("Marc", "Angle")


def test_split_principal_name_rejects_collective_references() -> None:
    assert split_principal_name("Dekker family") == ("", "")
    assert split_principal_name("Founders") == ("", "")
    assert split_principal_name("Solo") == ("", "")
    assert split_principal_name("") == ("", "")


def test_derive_contact_location_joins_present_parts() -> None:
    assert derive_contact_location("Bentonville", "AR", "United States") == \
        "Bentonville, AR, United States"
    assert derive_contact_location("London", "", "UK") == "London, UK"
    assert derive_contact_location("", "", "") == ""


def test_enrich_dataframe_adds_sample_parity_columns() -> None:
    df = pd.DataFrame(
        [
            {
                "website_url": "https://foo.com/", "website_ok": True,
                "website_status_code": 200, "primary_email": "",
                "principal_name": "Marc Angle", "city": "Boston",
                "state_region": "MA", "country": "United States",
            }
        ]
    ).fillna("")
    enriched = enrich_dataframe(df, {}, validation_period="2026-05")
    assert enriched.loc[0, "contact_first_name"] == "Marc"
    assert enriched.loc[0, "contact_last_name"] == "Angle"
    assert enriched.loc[0, "contact_full_name"] == "Marc Angle"
    assert enriched.loc[0, "contact_location"] == "Boston, MA, United States"
    assert enriched.loc[0, "secondary_email_validation_code"] == "no_secondary_evidence"
    assert (
        SECONDARY_CONTACT_UNCERTAINTY_NOTE
        in enriched.loc[0, "email_code_explanation_secondary"]
    )


def test_enrich_dataframe_skips_split_when_principal_is_collective() -> None:
    df = pd.DataFrame(
        [{"website_url": "https://foo.com/", "website_ok": True,
          "website_status_code": 200, "primary_email": "",
          "principal_name": "Dekker family", "city": "NYC", "state_region": "NY",
          "country": "United States"}]
    ).fillna("")
    enriched = enrich_dataframe(df, {}, validation_period="2026-05")
    assert enriched.loc[0, "contact_first_name"] == ""
    assert enriched.loc[0, "contact_last_name"] == ""
    # Full name is still set to the raw principal_name value (which IS what the
    # workbook stores, even when it's a collective).
    assert enriched.loc[0, "contact_full_name"] == "Dekker family"
    assert enriched.loc[0, "contact_location"] == "NYC, NY, United States"


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
