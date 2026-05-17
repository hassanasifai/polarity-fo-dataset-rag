from __future__ import annotations

from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from fo_dataset_pipeline.score_completion import (
    SAMPLE_COLUMNS_MAPPING,
    SCORE_DENOMINATOR,
    TEXT_SCORE_COLUMN,
    VISUAL_SCORE_COLUMN,
    _is_filled,
    add_completion_columns,
    app,
    compute_row_score,
    normalize_text_artifacts,
    render_visual,
)


def test_score_denominator_is_31() -> None:
    assert SCORE_DENOMINATOR == 31
    assert len(SAMPLE_COLUMNS_MAPPING) == 31


def test_is_filled_treats_blank_and_sentinels_as_empty() -> None:
    assert not _is_filled("")
    assert not _is_filled(None)
    assert not _is_filled(pd.NA)
    assert not _is_filled("nan")
    assert not _is_filled("no_secondary_evidence")
    assert _is_filled("actual value")
    assert _is_filled(0)
    assert _is_filled(False)  # False is a populated value


def test_render_visual_renders_block_count() -> None:
    assert render_visual(0) == "░" * 31
    assert render_visual(31) == "█" * 31
    out = render_visual(10)
    assert out.count("█") == 10
    assert out.count("░") == 21


def test_render_visual_clamps_out_of_range() -> None:
    assert render_visual(-5) == "░" * 31
    assert render_visual(100) == "█" * 31


def test_compute_row_score_full_row_returns_31() -> None:
    row = {our_col: f"value-{i}" for i, our_col in enumerate(SAMPLE_COLUMNS_MAPPING.values())}
    assert compute_row_score(row) == 31


def test_compute_row_score_empty_row_returns_2() -> None:
    # The two score columns themselves count as filled (we always populate them).
    row: dict = {}
    assert compute_row_score(row) == 2


def test_compute_row_score_partial() -> None:
    row = {
        "family_office_name": "Acme",
        "website_url": "https://acme.com",
        "family_office_domain": "acme.com",
        "url_quality": "Highest",
        "principal_name": "Jane Doe",
        "contact_first_name": "Jane",
        "contact_last_name": "Doe",
        "contact_full_name": "Jane Doe",
        "primary_email": "info@acme.com",
        "primary_email_validation_code": "mx_ok",
        "primary_email_code_explanation": "good",
        "primary_email_quality_assessment": "good_public_domain_mx",
        # All the rest left blank
    }
    score = compute_row_score(row)
    # 11 sample-mapped fields + 2 score-column auto-fills = 13.
    # (principal_name is NOT in the sample mapping; contact_full_name is.)
    assert score == 13


def test_add_completion_columns_populates_text_and_visual() -> None:
    df = pd.DataFrame(
        [
            {"family_office_name": "Acme", "website_url": "https://acme.com"},
            {"family_office_name": "", "website_url": ""},
        ]
    ).fillna("")
    enriched = add_completion_columns(df)
    assert TEXT_SCORE_COLUMN in enriched.columns
    assert VISUAL_SCORE_COLUMN in enriched.columns
    # Row 0: 2 populated cols + 2 auto = 4
    assert enriched.loc[0, TEXT_SCORE_COLUMN] == "4"
    # Row 1: only the 2 auto = 2
    assert enriched.loc[1, TEXT_SCORE_COLUMN] == "2"
    assert enriched.loc[0, VISUAL_SCORE_COLUMN].count("█") == 4


def test_normalize_text_artifacts_strips_integer_float_strings() -> None:
    df = pd.DataFrame(
        [{"employee_count": "843.0", "ratio": "12.5", "name": "Acme"}]
    )
    normalized = normalize_text_artifacts(df)
    assert normalized.loc[0, "employee_count"] == "843"
    assert normalized.loc[0, "ratio"] == "12.5"
    assert normalized.loc[0, "name"] == "Acme"


def test_cli_run_score_persists_to_csv(tmp_path: Path) -> None:
    dataset = tmp_path / "validated.csv"
    json_output = tmp_path / "validated.json"
    pd.DataFrame(
        [
            {
                "record_id": "fo_001",
                "family_office_name": "Acme",
                "website_url": "https://acme.com",
                "primary_email": "info@acme.com",
            }
        ]
    ).to_csv(dataset, index=False)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["--dataset", str(dataset), "--json-output", str(json_output)],
    )
    assert result.exit_code == 0, result.output
    df = pd.read_csv(dataset)
    assert int(df.loc[0, TEXT_SCORE_COLUMN]) >= 3
    assert "█" in df.loc[0, VISUAL_SCORE_COLUMN]
    assert json_output.exists()
