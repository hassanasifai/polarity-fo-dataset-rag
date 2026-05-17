from __future__ import annotations

from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from fo_dataset_pipeline.promote_addresses import (
    CONFIDENCE_COLUMN,
    EVIDENCE_COLUMN,
    _load_linkedin_streets,
    _load_places_streets,
    app,
    promote_row,
)


def test_load_places_streets_keys_by_domain_skips_closed(tmp_path: Path) -> None:
    csv = tmp_path / "places.csv"
    pd.DataFrame(
        [
            {"website": "https://foo.com/", "street": "1 Main St",
             "url": "https://maps.google.com/x",
             "temporarily_closed": False, "permanently_closed": False},
            {"website": "https://closed.com/", "street": "5 Other St",
             "url": "https://maps.google.com/y",
             "temporarily_closed": True, "permanently_closed": False},
            {"website": "", "street": "no domain",
             "url": "https://maps.google.com/z",
             "temporarily_closed": False, "permanently_closed": False},
        ]
    ).to_csv(csv, index=False)
    lookup = _load_places_streets(csv)
    assert set(lookup.keys()) == {"foo.com"}
    assert lookup["foo.com"]["street"] == "1 Main St"


def test_load_linkedin_streets_requires_company_url(tmp_path: Path) -> None:
    csv = tmp_path / "li.csv"
    pd.DataFrame(
        [
            {"website": "https://foo.com", "street": "1 Main",
             "linkedinUrl": "https://linkedin.com/company/foo"},
            {"website": "https://bar.com", "street": "2 Other",
             "linkedinUrl": "https://linkedin.com/in/someone"},
        ]
    ).to_csv(csv, index=False)
    lookup = _load_linkedin_streets(csv)
    assert set(lookup.keys()) == {"foo.com"}


def test_promote_row_prefers_places_over_linkedin() -> None:
    record = {"street_address": ""}
    places = {"street": "1 Places St", "evidence_url": "https://maps.google.com/x"}
    linkedin = {"street": "2 Linkedin St",
                "evidence_url": "https://linkedin.com/company/foo"}
    updates = promote_row(record, places, linkedin)
    assert updates["street_address"] == "1 Places St"
    assert updates[CONFIDENCE_COLUMN] == "google_places_domain_match"


def test_promote_row_falls_back_to_linkedin() -> None:
    record = {"street_address": ""}
    linkedin = {"street": "2 Linkedin St",
                "evidence_url": "https://linkedin.com/company/foo"}
    updates = promote_row(record, None, linkedin)
    assert updates["street_address"] == "2 Linkedin St"
    assert updates[CONFIDENCE_COLUMN] == "linkedin_company_page"
    assert updates[EVIDENCE_COLUMN] == "https://linkedin.com/company/foo"


def test_promote_row_does_not_overwrite_existing() -> None:
    record = {"street_address": "Existing 1 Main"}
    places = {"street": "1 Places St", "evidence_url": "https://maps.google.com/x"}
    assert promote_row(record, places, None) == {}


def test_promote_row_returns_empty_when_no_evidence() -> None:
    assert promote_row({"street_address": ""}, None, None) == {}


def test_cli_run_promotion_persists(tmp_path: Path) -> None:
    dataset = tmp_path / "validated.csv"
    pd.DataFrame(
        [
            {"record_id": "fo_001", "website_url": "https://foo.com",
             "street_address": ""},
            {"record_id": "fo_002", "website_url": "https://bar.com",
             "street_address": "Existing"},
        ]
    ).to_csv(dataset, index=False)
    places = tmp_path / "places.csv"
    pd.DataFrame(
        [
            {"website": "https://foo.com/", "street": "1 Places St",
             "url": "https://maps.google.com/x",
             "temporarily_closed": False, "permanently_closed": False},
        ]
    ).to_csv(places, index=False)
    li = tmp_path / "li.csv"
    pd.DataFrame(
        [
            {"website": "https://bar.com", "street": "2 LI St",
             "linkedinUrl": "https://linkedin.com/company/bar"},
        ]
    ).to_csv(li, index=False)
    json_output = tmp_path / "out.json"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--dataset", str(dataset),
            "--places-evidence", str(places),
            "--linkedin-evidence", str(li),
            "--json-output", str(json_output),
        ],
    )
    assert result.exit_code == 0, result.output

    df = pd.read_csv(dataset)
    row_001 = df[df["record_id"] == "fo_001"].iloc[0]
    row_002 = df[df["record_id"] == "fo_002"].iloc[0]
    assert row_001["street_address"] == "1 Places St"
    assert row_002["street_address"] == "Existing"
    assert json_output.exists()
