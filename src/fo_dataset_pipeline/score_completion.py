"""Compute the Data Completion Score against the sample workbook's denominator.

The PolarityIQ-supplied sample (``FO-MAX-data-sample-2.0.xlsx``) has 31 columns
and shows a score in the 19-29 range. To make our completion metric directly
comparable, we count populated cells across exactly those 31 sample columns
(mapped to our snake_case equivalents), NOT across our full 80+ column workbook.

Two columns are written per row:
- ``data_completion_score_text`` — integer 0-31 (matches sample format).
- ``data_completion_score_visual`` — unicode bar like
  ``█████████████████████████░░░░░░`` (25 filled blocks of 31).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

app = typer.Typer(no_args_is_help=True)

DEFAULT_DATASET_PATH = Path("data/processed/family_offices_validated.csv")
DEFAULT_JSON_OUTPUT = Path("data/processed/family_offices_validated.json")

# Mapping of sample-workbook column name (in evaluation order, minus the leading
# blank/sequence column) to our snake_case column. Used as the score denominator.
SAMPLE_COLUMNS_MAPPING: dict[str, str] = {
    "Family Office Name": "family_office_name",
    "Data Validation Period": "data_validation_period",
    "Data Completion Score (Text)": "data_completion_score_text",
    "Data Completion Score (Visual)": "data_completion_score_visual",
    "Family Office Description": "description",
    "Investment Thesis": "investment_thesis",
    "Investing Sectors": "investing_sectors",
    "Family Office Domain": "family_office_domain",
    "Family Office Website Address": "website_url",
    "URL Quality": "url_quality",
    "Corporate LinkedIn Address": "corporate_linkedin_url",
    "Family Office Street Address": "street_address",
    "Family Office City": "city",
    "Family Office State / Region": "state_region",
    "Family Office Country": "country",
    "Contact First Name": "contact_first_name",
    "Contact Last Name": "contact_last_name",
    "Contact Full Name": "contact_full_name",
    "Contact Job Title": "principal_title",
    "Contact Location": "contact_location",
    "Contact LinkedIn Profile": "principal_linkedin_url",
    "Contact Primary Email": "primary_email",
    "Primary E-Mail Validation Code": "primary_email_validation_code",
    "Primary E-Mail Code Explanation": "primary_email_code_explanation",
    "Email Quality Assessment (Primary)": "primary_email_quality_assessment",
    "Primary Phone Number": "primary_phone",
    "Contact Secondary Email": "contact_secondary_email",
    "Secondary E-Mail Validation Code": "secondary_email_validation_code",
    "E-Mail Code Explanation (Secondary)": "email_code_explanation_secondary",
    "Email Quality Assessment (Secondary)": "email_quality_assessment_secondary",
    "Secondary Phone Number": "contact_secondary_phone",
}

SCORE_DENOMINATOR = len(SAMPLE_COLUMNS_MAPPING)  # = 31

TEXT_SCORE_COLUMN = "data_completion_score_text"
VISUAL_SCORE_COLUMN = "data_completion_score_visual"

NULLISH_SENTINELS = {
    "", "nan", "none", "null", "no_secondary_evidence",
}
TRAILING_ZERO_DECIMAL = re.compile(r"^-?\d+\.0$")


def _is_filled(value: object) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    text = str(value).strip().lower()
    if not text:
        return False
    if text in NULLISH_SENTINELS:
        return False
    return True


def compute_row_score(row: dict) -> int:
    """Return the count (0..31) of populated cells across the sample columns."""
    score = 0
    for our_col in SAMPLE_COLUMNS_MAPPING.values():
        if our_col in (TEXT_SCORE_COLUMN, VISUAL_SCORE_COLUMN):
            # Self-referential — count as filled if other 29 columns yield a
            # score, but to avoid bootstrapping we always count the two score
            # columns as filled (they are deterministically populated by us).
            score += 1
            continue
        if _is_filled(row.get(our_col)):
            score += 1
    return score


def render_visual(score: int, total: int = SCORE_DENOMINATOR) -> str:
    score = max(0, min(total, score))
    return "█" * score + "░" * (total - score)


def normalize_text_artifacts(df: pd.DataFrame) -> pd.DataFrame:
    """Remove CSV float artifacts like ``843.0`` from integer-like text cells."""
    return df.map(
        lambda value: value[:-2]
        if isinstance(value, str) and TRAILING_ZERO_DECIMAL.match(value.strip())
        else value
    )


def add_completion_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for column in (TEXT_SCORE_COLUMN, VISUAL_SCORE_COLUMN):
        df[column] = ""

    for index, row in df.iterrows():
        score = compute_row_score(row.to_dict())
        df.at[index, TEXT_SCORE_COLUMN] = str(score)
        df.at[index, VISUAL_SCORE_COLUMN] = render_visual(score)
    return df


@app.command("run")
def run_score(
    dataset: Annotated[Path, typer.Option("--dataset")] = DEFAULT_DATASET_PATH,
    json_output: Annotated[Path | None, typer.Option("--json-output")] = DEFAULT_JSON_OUTPUT,
) -> None:
    """Compute Data Completion Score against the sample's 31-column denominator."""
    if not dataset.exists():
        raise typer.BadParameter(f"dataset not found: {dataset}")
    df = pd.read_csv(dataset, dtype=str).fillna("")
    df = normalize_text_artifacts(df)
    df = add_completion_columns(df)
    df.to_csv(dataset, index=False)

    if json_output is not None:
        import json
        json_output.write_text(
            json.dumps(df.to_dict(orient="records"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    scores = df[TEXT_SCORE_COLUMN].astype(int)
    typer.echo(
        f"Data Completion Score computed for {len(df)} rows. "
        f"min={scores.min()}, median={int(scores.median())}, "
        f"max={scores.max()}, denominator={SCORE_DENOMINATOR}."
    )


if __name__ == "__main__":
    app()
