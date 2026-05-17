from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from fo_dataset_pipeline.promote_social_media import (
    CONFIDENCE_VALUE,
    EVIDENCE_COLUMN,
    PLATFORM_COLUMNS,
    PROMOTED_COLUMNS,
    _first_url_on_platform,
    _parse_url_list,
    app,
    load_contact_lookup,
    promote_row,
)


def test_parse_url_list_handles_list_literal() -> None:
    raw = "['https://twitter.com/foo', 'https://twitter.com/bar']"
    assert _parse_url_list(raw) == ["https://twitter.com/foo", "https://twitter.com/bar"]


def test_parse_url_list_handles_empty_and_nullish() -> None:
    assert _parse_url_list("") == []
    assert _parse_url_list("[]") == []
    assert _parse_url_list(None) == []
    assert _parse_url_list(pd.NA) == []


def test_parse_url_list_recovers_bare_url_string() -> None:
    assert _parse_url_list("https://twitter.com/foo") == ["https://twitter.com/foo"]


def test_first_url_on_platform_filters_by_host() -> None:
    urls = ["https://example.com/foo", "https://www.tiktok.com/@bar",
            "https://twitter.com/baz"]
    assert _first_url_on_platform(urls, ("tiktok.com",)) == "https://www.tiktok.com/@bar"
    assert _first_url_on_platform(urls, ("twitter.com", "x.com")) == "https://twitter.com/baz"
    assert _first_url_on_platform(urls, ("youtube.com",)) is None


def test_promote_row_skips_when_domain_mismatch() -> None:
    record = {"website_url": "https://acme.com"}
    contact = {
        "originalStartUrl": "https://different.com/",
        "twitters": "['https://twitter.com/acme']",
    }
    assert promote_row(record, contact) == {}


def test_promote_row_promotes_each_platform_only_when_host_matches() -> None:
    record = {"website_url": "https://acme.com"}
    contact = {
        "originalStartUrl": "https://acme.com/",
        "twitters": "['https://twitter.com/acme']",
        "instagrams": "['https://www.instagram.com/acme']",
        "facebooks": "['https://example.com/not-real-facebook']",  # bad host
        "youtubes": "['https://www.youtube.com/@acme']",
        "tiktoks": "[]",
    }
    updates = promote_row(record, contact)
    assert updates["twitter_url"] == "https://twitter.com/acme"
    assert updates["instagram_url"] == "https://www.instagram.com/acme"
    assert "facebook_url" not in updates  # rejected by host filter
    assert updates["youtube_url"] == "https://www.youtube.com/@acme"
    assert "tiktok_url" not in updates
    assert updates[EVIDENCE_COLUMN] == "https://acme.com/"
    assert updates["social_media_confidence"] == CONFIDENCE_VALUE


def test_promote_row_does_not_overwrite_existing_values() -> None:
    record = {
        "website_url": "https://acme.com",
        "twitter_url": "https://twitter.com/existing",
    }
    contact = {
        "originalStartUrl": "https://acme.com/",
        "twitters": "['https://twitter.com/new']",
        "instagrams": "['https://www.instagram.com/acme']",
    }
    updates = promote_row(record, contact)
    assert "twitter_url" not in updates
    assert updates["instagram_url"] == "https://www.instagram.com/acme"


def test_promote_row_returns_empty_when_no_platforms_match() -> None:
    record = {"website_url": "https://acme.com"}
    contact = {
        "originalStartUrl": "https://acme.com/",
        "twitters": "[]",
        "instagrams": "[]",
        "facebooks": "[]",
    }
    assert promote_row(record, contact) == {}


def test_load_contact_lookup_keys_by_domain(tmp_path: Path) -> None:
    csv = tmp_path / "contact_raw.csv"
    pd.DataFrame(
        [
            {"originalStartUrl": "https://www.foo.com/", "domain": "foo.com",
             "twitters": "['https://twitter.com/foo']"},
            {"originalStartUrl": "https://bar.io/", "domain": "bar.io",
             "facebooks": "['https://facebook.com/bar']"},
        ]
    ).to_csv(csv, index=False)
    lookup = load_contact_lookup(csv)
    assert set(lookup.keys()) == {"foo.com", "bar.io"}


def test_run_promotion_writes_csv_and_json(tmp_path: Path) -> None:
    dataset = tmp_path / "validated.csv"
    pd.DataFrame(
        [
            {
                "record_id": "fo_001",
                "family_office_name": "Acme",
                "website_url": "https://acme.com",
            }
        ]
    ).to_csv(dataset, index=False)
    contact_csv = tmp_path / "contact_raw.csv"
    pd.DataFrame(
        [
            {
                "originalStartUrl": "https://acme.com/",
                "domain": "acme.com",
                "twitters": "['https://twitter.com/acme']",
                "instagrams": "['https://www.instagram.com/acme']",
                "facebooks": "[]",
                "youtubes": "[]",
                "tiktoks": "[]",
            }
        ]
    ).to_csv(contact_csv, index=False)
    json_output = tmp_path / "out.json"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--dataset", str(dataset),
            "--contact-raw", str(contact_csv),
            "--json-output", str(json_output),
        ],
    )
    assert result.exit_code == 0, result.output

    df = pd.read_csv(dataset)
    assert df.loc[0, "twitter_url"] == "https://twitter.com/acme"
    assert df.loc[0, "instagram_url"] == "https://www.instagram.com/acme"
    assert df.loc[0, EVIDENCE_COLUMN] == "https://acme.com/"
    for column in PROMOTED_COLUMNS:
        assert column in df.columns
    rows = json.loads(json_output.read_text(encoding="utf-8"))
    assert rows[0]["twitter_url"] == "https://twitter.com/acme"
    assert "instagram_url" in PLATFORM_COLUMNS
