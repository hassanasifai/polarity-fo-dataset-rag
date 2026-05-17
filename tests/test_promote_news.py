from __future__ import annotations

import pandas as pd
from typer.testing import CliRunner

from fo_dataset_pipeline.promote_news import (
    _name_tokens,
    app,
    format_recent_activity,
    is_blocked_source,
    parse_recent_activity_text,
    select_signal,
    title_matches_name,
)


def test_name_tokens_drops_stopwords_and_short_tokens() -> None:
    assert _name_tokens("Cat Trail Capital") == {"cat", "trail"}


def test_name_tokens_falls_back_when_all_tokens_filtered() -> None:
    # "CM Wealth": cm is length 2, wealth is stopword
    tokens = _name_tokens("CM Wealth")
    assert "cm" in tokens


def test_title_matches_name_requires_all_tokens() -> None:
    assert title_matches_name("Cat Trail Capital announces new hire", "Cat Trail Capital")
    assert not title_matches_name("Cat Capital announces", "Cat Trail Capital")


def test_is_blocked_source_catches_directories() -> None:
    assert is_blocked_source("PitchBook.com")
    assert is_blocked_source("Crunchbase.com")
    assert not is_blocked_source("Wall Street Journal")
    assert not is_blocked_source("")


def test_select_signal_returns_most_recent_matching_row() -> None:
    news = pd.DataFrame(
        [
            {"family_office_name": "Acme FO", "title": "Acme FO names new CEO",
             "articleUrl": "https://news.com/a", "sourceName": "WSJ",
             "pubDate": "Mon, 03 Mar 2025 10:00:00 GMT", "link": "", "error": None},
            {"family_office_name": "Acme FO", "title": "Acme FO opens office",
             "articleUrl": "https://news.com/b", "sourceName": "WSJ",
             "pubDate": "Wed, 03 Sep 2025 10:00:00 GMT", "link": "", "error": None},
            {"family_office_name": "Other FO", "title": "Other thing",
             "articleUrl": "https://news.com/c", "sourceName": "WSJ",
             "pubDate": "Wed, 03 Sep 2025 10:00:00 GMT", "link": "", "error": None},
        ]
    )
    signal = select_signal(news, "Acme FO")
    assert signal is not None
    assert signal["title"] == "Acme FO opens office"
    assert signal["pub_date"] == "2025-09-03"


def test_select_signal_filters_old_dates() -> None:
    news = pd.DataFrame(
        [{"family_office_name": "Acme FO", "title": "Acme FO from long ago",
          "articleUrl": "https://news.com/a", "sourceName": "WSJ",
          "pubDate": "Mon, 03 Mar 2024 10:00:00 GMT", "link": "", "error": None}]
    )
    assert select_signal(news, "Acme FO") is None


def test_select_signal_filters_blocked_sources() -> None:
    news = pd.DataFrame(
        [{"family_office_name": "Acme FO", "title": "Acme FO news",
          "articleUrl": "https://news.com/a", "sourceName": "pitchbook.com",
          "pubDate": "Mon, 03 Mar 2025 10:00:00 GMT", "link": "", "error": None}]
    )
    assert select_signal(news, "Acme FO") is None


def test_select_signal_filters_non_matching_titles() -> None:
    news = pd.DataFrame(
        [{"family_office_name": "Acme FO", "title": "Generic industry roundup",
          "articleUrl": "https://news.com/a", "sourceName": "WSJ",
          "pubDate": "Mon, 03 Mar 2025 10:00:00 GMT", "link": "", "error": None}]
    )
    assert select_signal(news, "Acme FO") is None


def test_select_signal_filters_error_rows() -> None:
    news = pd.DataFrame(
        [{"family_office_name": "Acme FO", "title": None,
          "articleUrl": None, "sourceName": None,
          "pubDate": None, "link": None, "error": True}]
    )
    assert select_signal(news, "Acme FO") is None


def test_format_recent_activity_renders_url_when_present() -> None:
    signal = {"title": "Headline", "url": "https://x.com/a",
              "source_name": "Bloomberg", "pub_date": "2025-04-01"}
    text = format_recent_activity(signal)
    assert "Bloomberg" in text and "2025-04-01" in text and "https://x.com/a" in text


def test_parse_recent_activity_text_extracts_metadata() -> None:
    parsed = parse_recent_activity_text(
        "Acme hires CIO (Business Wire, 2025-05-01) — https://news.com/a"
    )
    assert parsed is not None
    assert parsed["recent_activity_date"] == "2025-05-01"
    assert parsed["recent_activity_outlet"] == "Business Wire"
    assert parsed["recent_activity_url"] == "https://news.com/a"
    assert parsed["recent_activity_type"] == "news"


def test_run_news_promotion_populates_and_clears_stale_note(tmp_path) -> None:
    dataset = tmp_path / "validated.csv"
    pd.DataFrame(
        [{
            "record_id": "fo_001", "family_office_name": "Acme FO",
            "website_url": "https://acme.com", "recent_activity": "",
            "uncertainty_notes": "earlier note; no recent public signal as of 2026-05-17",
        }]
    ).to_csv(dataset, index=False)
    news = tmp_path / "news.csv"
    pd.DataFrame(
        [{"family_office_name": "Acme FO", "title": "Acme FO names new CEO",
          "articleUrl": "https://news.com/a", "sourceName": "WSJ",
          "pubDate": "Mon, 03 Mar 2025 10:00:00 GMT", "link": "", "error": None}]
    ).to_csv(news, index=False)
    json_path = tmp_path / "out.json"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--dataset", str(dataset),
            "--news", str(news),
            "--json-output", str(json_path),
        ],
    )
    assert result.exit_code == 0, result.output

    df = pd.read_csv(dataset)
    row = df.iloc[0]
    assert "Acme FO" in str(row["recent_activity"])
    assert row["recent_activity_date"] == "2025-03-03"
    assert row["recent_activity_outlet"] == "WSJ"
    assert row["recent_activity_url"] == "https://news.com/a"
    assert row["recent_activity_type"] == "news"
    assert "no recent public signal" not in str(row["uncertainty_notes"])
    assert "earlier note" in str(row["uncertainty_notes"])


def test_run_news_promotion_backfills_metadata_for_existing_activity(tmp_path) -> None:
    dataset = tmp_path / "validated.csv"
    pd.DataFrame(
        [{
            "record_id": "fo_001", "family_office_name": "Acme FO",
            "website_url": "https://acme.com",
            "recent_activity": "Acme FO launches fund (Reuters, 2025-08-15) — https://r.com/a",
            "uncertainty_notes": "",
        }]
    ).to_csv(dataset, index=False)
    news = tmp_path / "news.csv"
    pd.DataFrame(
        [{"family_office_name": "Acme FO", "title": None, "articleUrl": None,
          "sourceName": None, "pubDate": None, "link": None, "error": True}]
    ).to_csv(news, index=False)
    json_path = tmp_path / "out.json"

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["--dataset", str(dataset), "--news", str(news), "--json-output", str(json_path)],
    )
    assert result.exit_code == 0, result.output

    df = pd.read_csv(dataset)
    row = df.iloc[0]
    assert row["recent_activity_date"] == "2025-08-15"
    assert row["recent_activity_outlet"] == "Reuters"
    assert row["recent_activity_url"] == "https://r.com/a"
    assert json_path.exists()


def test_run_news_promotion_marks_none_found(tmp_path) -> None:
    dataset = tmp_path / "validated.csv"
    pd.DataFrame(
        [{"record_id": "fo_001", "family_office_name": "Acme FO",
          "website_url": "https://acme.com", "recent_activity": "",
          "uncertainty_notes": ""}]
    ).to_csv(dataset, index=False)
    news = tmp_path / "news.csv"
    pd.DataFrame(
        [{"family_office_name": "Acme FO", "title": None, "articleUrl": None,
          "sourceName": None, "pubDate": None, "link": None, "error": True}]
    ).to_csv(news, index=False)
    json_path = tmp_path / "out.json"

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["--dataset", str(dataset), "--news", str(news), "--json-output", str(json_path)],
    )
    assert result.exit_code == 0, result.output

    df = pd.read_csv(dataset)
    row = df.iloc[0]
    assert row["recent_activity_type"] == "none_found"
    assert row["recent_activity_confidence"] == "no_qualifying_public_signal"
    assert json_path.exists()
