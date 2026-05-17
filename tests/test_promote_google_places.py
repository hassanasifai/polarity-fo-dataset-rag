from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from fo_dataset_pipeline.promote_google_places import (
    CONFIDENCE_VALUE,
    EVIDENCE_COLUMN,
    PHONE_CORROBORATION_COLUMN,
    PROMOTED_COLUMNS,
    _digits_only,
    _phones_match,
    app,
    load_places_lookup,
    promote_row,
)


def test_digits_only_strips_punctuation() -> None:
    assert _digits_only("(203) 992-4630") == "2039924630"
    assert _digits_only("+44 20 3770 2710") == "442037702710"
    assert _digits_only(None) == ""
    assert _digits_only(pd.NA) == ""


def test_phones_match_compares_last_10_digits() -> None:
    assert _phones_match("(203) 992-4630", "+12039924630") is True
    assert _phones_match("415-555-1234", "(415) 555-1234") is True
    assert _phones_match("415-555-1234", "415-555-9999") is False
    assert _phones_match("", "415-555-1234") is False


def test_load_places_lookup_keys_by_returned_website_domain(tmp_path: Path) -> None:
    csv = tmp_path / "places.csv"
    pd.DataFrame(
        [
            {"website": "https://acme.com/", "url": "https://maps.google.com/1",
             "temporarily_closed": False, "permanently_closed": False},
            {"website": "http://www.acme.com/", "url": "https://maps.google.com/2",
             "temporarily_closed": False, "permanently_closed": False},
            {"website": "", "url": "https://maps.google.com/3",
             "temporarily_closed": False, "permanently_closed": False},
        ]
    ).to_csv(csv, index=False)
    lookup = load_places_lookup(csv)
    assert "acme.com" in lookup


def test_load_places_lookup_skips_closed_listings(tmp_path: Path) -> None:
    csv = tmp_path / "places.csv"
    pd.DataFrame(
        [
            {"website": "https://closed.com/", "url": "https://maps.google.com/x",
             "temporarily_closed": True, "permanently_closed": False},
            {"website": "https://gone.com/", "url": "https://maps.google.com/y",
             "temporarily_closed": False, "permanently_closed": True},
        ]
    ).to_csv(csv, index=False)
    lookup = load_places_lookup(csv)
    assert lookup == {}


def test_promote_row_refuses_when_website_domain_mismatches() -> None:
    """The scraper sometimes returns a different business — reject when so."""
    record = {"website_url": "https://ralph-family-office.com"}
    places_row = {
        "website": "http://pmfo.global/",  # Pall Mall, NOT Ralph
        "url": "https://maps.google.com/x",
        "phone": "+44 20 3770 2710",
        "reviews_count": 9,
        "total_score": 4.5,
        "category_name": "Investment service",
    }
    assert promote_row(record, places_row) == {}


def test_promote_row_promotes_when_domain_matches() -> None:
    record = {"website_url": "https://sjsinvest.com"}
    places_row = {
        "website": "https://www.sjsinvest.com/",
        "url": "https://maps.google.com/sjs",
        "phone": "(419) 885-2626",
        "phone_unformatted": "+14198852626",
        "reviews_count": 4.0,
        "total_score": 5.0,
        "category_name": "Investment service",
    }
    updates = promote_row(record, places_row)
    assert updates["google_places_phone"] == "(419) 885-2626"
    assert updates["google_places_reviews_count"] == "4"
    assert updates["google_places_rating"] == "5.0"
    assert updates["google_places_category"] == "Investment service"
    assert updates[EVIDENCE_COLUMN] == "https://maps.google.com/sjs"
    assert updates["google_places_confidence"] == CONFIDENCE_VALUE


def test_promote_row_flags_phone_corroboration_match() -> None:
    record = {
        "website_url": "https://sjsinvest.com",
        "primary_phone": "(419) 885-2626",
    }
    places_row = {
        "website": "https://www.sjsinvest.com/",
        "url": "https://maps.google.com/sjs",
        "phone": "(419) 885-2626",
        "phone_unformatted": "+14198852626",
    }
    updates = promote_row(record, places_row)
    assert updates[PHONE_CORROBORATION_COLUMN] == "True"


def test_promote_row_flags_phone_corroboration_conflict() -> None:
    record = {
        "website_url": "https://sjsinvest.com",
        "primary_phone": "(419) 555-0000",  # different
    }
    places_row = {
        "website": "https://www.sjsinvest.com/",
        "url": "https://maps.google.com/sjs",
        "phone": "(419) 885-2626",
    }
    updates = promote_row(record, places_row)
    assert updates[PHONE_CORROBORATION_COLUMN] == "False"


def test_promote_row_does_not_overwrite_existing_values() -> None:
    record = {
        "website_url": "https://sjsinvest.com",
        "google_places_category": "Existing Category",
    }
    places_row = {
        "website": "https://www.sjsinvest.com/",
        "url": "https://maps.google.com/sjs",
        "phone": "(419) 885-2626",
        "category_name": "New Category",
    }
    updates = promote_row(record, places_row)
    assert "google_places_category" not in updates
    assert updates["google_places_phone"] == "(419) 885-2626"


def test_promote_row_returns_empty_when_no_places_row() -> None:
    assert promote_row({"website_url": "https://acme.com"}, None) == {}


def test_promote_row_returns_empty_when_evidence_url_missing() -> None:
    record = {"website_url": "https://acme.com"}
    places_row = {"website": "https://acme.com", "url": "", "phone": "555-1234"}
    assert promote_row(record, places_row) == {}


def test_run_promotion_writes_csv_and_json(tmp_path: Path) -> None:
    dataset = tmp_path / "validated.csv"
    pd.DataFrame(
        [
            {
                "record_id": "fo_001",
                "family_office_name": "SJS",
                "website_url": "https://sjsinvest.com",
                "primary_phone": "(419) 885-2626",
            }
        ]
    ).to_csv(dataset, index=False)
    places_csv = tmp_path / "places.csv"
    pd.DataFrame(
        [
            {
                "website": "https://www.sjsinvest.com/",
                "url": "https://maps.google.com/sjs",
                "phone": "(419) 885-2626",
                "phone_unformatted": "+14198852626",
                "reviews_count": 4,
                "total_score": 5.0,
                "category_name": "Investment service",
                "temporarily_closed": False,
                "permanently_closed": False,
            }
        ]
    ).to_csv(places_csv, index=False)
    json_output = tmp_path / "out.json"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--dataset", str(dataset),
            "--places-evidence", str(places_csv),
            "--json-output", str(json_output),
        ],
    )
    assert result.exit_code == 0, result.output

    df = pd.read_csv(dataset)
    assert df.loc[0, "google_places_phone"] == "(419) 885-2626"
    assert float(df.loc[0, "google_places_rating"]) == 5.0
    assert bool(df.loc[0, PHONE_CORROBORATION_COLUMN]) is True
    for column in PROMOTED_COLUMNS:
        assert column in df.columns
    rows = json.loads(json_output.read_text(encoding="utf-8"))
    assert rows[0]["google_places_phone"] == "(419) 885-2626"
