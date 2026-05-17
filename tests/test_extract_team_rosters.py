from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from fo_dataset_pipeline.extract_team_rosters import (
    _is_plausible_name,
    _is_role_line,
    app,
    extract_from_markdown,
)


def test_is_plausible_name_accepts_two_token_titlecase() -> None:
    assert _is_plausible_name("David Dekker")
    assert _is_plausible_name("Russell W. Dekker")
    assert _is_plausible_name("Andrew Budinoff")


def test_is_plausible_name_rejects_section_headings() -> None:
    assert not _is_plausible_name("Our Team")
    assert not _is_plausible_name("About Us")
    assert not _is_plausible_name("Investment Management")
    assert not _is_plausible_name("Family Office")


def test_is_plausible_name_rejects_too_few_or_too_many_tokens() -> None:
    assert not _is_plausible_name("Solo")
    assert not _is_plausible_name("A B C D E F")


def test_is_plausible_name_rejects_lowercase_or_all_caps() -> None:
    assert not _is_plausible_name("john doe")
    assert not _is_plausible_name("DAVID DEKKER")


def test_is_role_line_detects_known_roles() -> None:
    assert _is_role_line("Managing Partner")
    assert _is_role_line("Founder & CEO")
    assert _is_role_line("Chief Investment Officer")
    assert _is_role_line("Head of Research")
    assert _is_role_line("Trustee")


def test_is_role_line_rejects_non_roles() -> None:
    assert not _is_role_line("New York, NY")
    assert not _is_role_line("Lorem ipsum dolor sit")


def test_extract_from_markdown_bold_pattern() -> None:
    md = (
        "Our Leadership\n\n"
        "**David Dekker**, Managing Partner — leads the firm.\n"
        "**Russell W. Dekker**, Partner — focuses on real assets.\n"
    )
    result = dict(extract_from_markdown(md))
    assert result["David Dekker"].startswith("Managing Partner")
    assert "Partner" in result["Russell W. Dekker"]


def test_extract_from_markdown_heading_then_role() -> None:
    md = (
        "### David Dekker\n"
        "Managing Partner & Founder\n\n"
        "Some bio text here.\n\n"
        "### Andrew Budinoff\n"
        "Director of Investments\n"
    )
    result = dict(extract_from_markdown(md))
    assert "David Dekker" in result
    assert "Andrew Budinoff" in result
    assert "Director" in result["Andrew Budinoff"]


def test_extract_from_markdown_ignores_section_heading_as_name() -> None:
    md = (
        "### Our Team\n"
        "Managing Partner here.\n\n"
        "### About\n"
        "We do things.\n"
    )
    assert extract_from_markdown(md) == []


def test_extract_from_markdown_dedupes_repeated_names() -> None:
    md = (
        "**David Dekker**, Managing Partner.\n"
        "\n"
        "### David Dekker\n"
        "Managing Partner\n"
    )
    result = extract_from_markdown(md)
    names = [name for name, _ in result]
    assert names.count("David Dekker") == 1


def test_run_extraction_writes_team_rosters_csv(tmp_path: Path) -> None:
    dataset_csv = tmp_path / "validated.csv"
    pd.DataFrame(
        [
            {
                "record_id": "fo_001",
                "family_office_name": "Acme",
                "website_url": "https://acme.com",
            },
            {
                "record_id": "fo_002",
                "family_office_name": "Other",
                "website_url": "https://other.com",
            },
        ]
    ).to_csv(dataset_csv, index=False)

    firecrawl_json = tmp_path / "firecrawl.json"
    firecrawl_json.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "markdown": (
                            "### David Dekker\nManaging Partner\n\n"
                            "**Andrew Budinoff**, Director of Investments\n"
                        ),
                        "metadata": {"sourceURL": "https://acme.com/team"},
                    },
                    {
                        "markdown": "## Welcome\nNo names here.\n",
                        "metadata": {"sourceURL": "https://acme.com/home"},
                    },
                    {
                        "markdown": "**Unknown Person**, Random Title\n",
                        "metadata": {"sourceURL": "https://stranger.com/team"},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    output_csv = tmp_path / "out.csv"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--firecrawl-path", str(firecrawl_json),
            "--dataset", str(dataset_csv),
            "--output", str(output_csv),
        ],
    )
    assert result.exit_code == 0, result.output

    df = pd.read_csv(output_csv)
    assert len(df) == 2  # David and Andrew
    assert set(df["principal_name"]) == {"David Dekker", "Andrew Budinoff"}
    assert (df["record_id"] == "fo_001").all()  # Stranger excluded (no domain match)
    assert (df["extraction_method"] == "firecrawl_markdown_pattern_match").all()
