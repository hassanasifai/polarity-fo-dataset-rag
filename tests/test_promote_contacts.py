from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from fo_dataset_pipeline.promote_contacts import (
    PROMOTED_COLUMNS,
    app,
    load_contact_lookup,
    load_linkedin_lookup,
    pick_company_linkedin,
    pick_corporate_email,
    pick_phone,
    promote_row,
)


def test_pick_corporate_email_prefers_info_address() -> None:
    emails = "manager.research@aspiriant.com; info@aspiriant.com"
    assert pick_corporate_email(emails, "aspiriant.com") == "info@aspiriant.com"


def test_pick_corporate_email_uses_prefix_match() -> None:
    emails = "information@example.com"
    assert pick_corporate_email(emails, "example.com") == "information@example.com"


def test_pick_corporate_email_returns_none_for_personal_only() -> None:
    emails = "jsmith@aspiriant.com; jane.doe@aspiriant.com"
    assert pick_corporate_email(emails, "aspiriant.com") is None


def test_pick_corporate_email_handles_nan() -> None:
    import pandas as pd
    assert pick_corporate_email(pd.NA, "x.com") is None
    assert pick_corporate_email(None, "x.com") is None
    assert pick_corporate_email("", "x.com") is None


def test_pick_phone_returns_first_with_enough_digits() -> None:
    assert pick_phone("123; 415-226-4170; +44 20 7000 0000") == "415-226-4170"


def test_pick_phone_returns_none_when_no_valid_number() -> None:
    assert pick_phone("123; abc; 45") is None
    assert pick_phone(None) is None


def test_pick_company_linkedin_only_company_urls() -> None:
    field = "https://linkedin.com/in/jsmith; https://linkedin.com/company/foo"
    assert pick_company_linkedin(field) == "https://linkedin.com/company/foo"


def test_pick_company_linkedin_returns_none_for_personal_only() -> None:
    assert pick_company_linkedin("https://linkedin.com/in/jsmith") is None


def test_promote_row_skips_when_record_already_has_value() -> None:
    record = {
        "website_url": "https://acme.com",
        "primary_email": "existing@acme.com",
        "primary_phone": "5555555555",
        "corporate_linkedin_url": "https://linkedin.com/company/acme",
    }
    contact = {
        "original_start_url": "https://acme.com",
        "emails": "info@acme.com",
        "phones": "1234567890",
        "linkedins": "https://linkedin.com/company/acme-2",
    }
    updates = promote_row(record, contact, None)
    assert updates == {}


def test_promote_row_promotes_when_evidence_available() -> None:
    record = {"website_url": "https://acme.com", "primary_email": "",
              "primary_phone": "", "corporate_linkedin_url": ""}
    contact = {
        "original_start_url": "https://acme.com/",
        "emails": "info@acme.com",
        "phones": "415-555-1234",
        "linkedins": "https://linkedin.com/company/acme",
    }
    updates = promote_row(record, contact, None)
    assert updates["primary_email"] == "info@acme.com"
    assert updates["primary_email_evidence_url"] == "https://acme.com/"
    assert updates["primary_email_confidence"] == "corporate_public_listed"
    assert updates["primary_phone"] == "415-555-1234"
    assert updates["corporate_linkedin_url"] == "https://linkedin.com/company/acme"
    assert updates["corporate_linkedin_confidence"] == "linked_from_official_site"


def test_promote_row_prefers_linkedin_scraper_evidence() -> None:
    record = {"website_url": "https://acme.com", "primary_email": "",
              "primary_phone": "", "corporate_linkedin_url": ""}
    linkedin = {
        "website": "https://acme.com",
        "linkedinUrl": "https://www.linkedin.com/company/acme-official",
    }
    updates = promote_row(record, None, linkedin)
    assert updates["corporate_linkedin_url"] == "https://www.linkedin.com/company/acme-official"
    assert updates["corporate_linkedin_confidence"] == "linkedin_scraped_match"


def test_load_contact_lookup_keys_by_domain(tmp_path: Path) -> None:
    csv = tmp_path / "contact.csv"
    pd.DataFrame(
        [
            {"original_start_url": "https://www.foo.com/", "emails": "info@foo.com"},
            {"original_start_url": "https://bar.io/", "emails": "hi@bar.io"},
        ]
    ).to_csv(csv, index=False)
    lookup = load_contact_lookup(csv)
    assert set(lookup.keys()) == {"foo.com", "bar.io"}


def test_load_linkedin_lookup_only_company_urls(tmp_path: Path) -> None:
    csv = tmp_path / "li.csv"
    pd.DataFrame(
        [
            {"website": "https://foo.com", "linkedinUrl": "https://linkedin.com/company/foo"},
            {"website": "https://bar.com", "linkedinUrl": "https://linkedin.com/in/somebody"},
            {"website": "https://baz.com", "linkedinUrl": ""},
        ]
    ).to_csv(csv, index=False)
    lookup = load_linkedin_lookup(csv)
    assert set(lookup.keys()) == {"foo.com"}


def test_run_promotion_writes_csv_and_json(tmp_path: Path) -> None:
    dataset = tmp_path / "validated.csv"
    pd.DataFrame(
        [
            {
                "record_id": "fo_001",
                "family_office_name": "Acme",
                "website_url": "https://acme.com",
                "primary_email": "",
                "primary_phone": "",
                "corporate_linkedin_url": "",
            },
        ]
    ).to_csv(dataset, index=False)
    contact_csv = tmp_path / "contact.csv"
    pd.DataFrame(
        [
            {
                "original_start_url": "https://acme.com",
                "emails": "info@acme.com",
                "phones": "415-555-9999",
                "linkedins": "https://linkedin.com/company/acme",
            }
        ]
    ).to_csv(contact_csv, index=False)
    linkedin_csv = tmp_path / "li.csv"
    pd.DataFrame(
        [{"website": "https://acme.com",
          "linkedinUrl": "https://linkedin.com/company/acme-official"}]
    ).to_csv(linkedin_csv, index=False)
    json_output = tmp_path / "out.json"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--dataset", str(dataset),
            "--contact-evidence", str(contact_csv),
            "--linkedin-evidence", str(linkedin_csv),
            "--json-output", str(json_output),
        ],
    )
    assert result.exit_code == 0, result.output

    df = pd.read_csv(dataset)
    assert df.loc[0, "primary_email"] == "info@acme.com"
    assert (
        df.loc[0, "corporate_linkedin_url"]
        == "https://linkedin.com/company/acme-official"
    )
    for column in PROMOTED_COLUMNS:
        assert column in df.columns
    rows = json.loads(json_output.read_text(encoding="utf-8"))
    assert rows[0]["primary_email"] == "info@acme.com"
