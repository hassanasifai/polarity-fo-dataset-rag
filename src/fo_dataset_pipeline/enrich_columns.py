"""Final pass — add sample-workbook-parity columns to data_50.

Adds columns derivable from data already on disk (no new network calls):

- ``data_validation_period`` — fixed string identifying the validation cycle.
- ``family_office_domain`` — bare domain derived from ``website_url``.
- ``url_quality`` — Highest / Medium / Low / Failed, mapped from website checks.
- ``primary_email_validation_code`` — joined from email_validation_evidence.
- ``primary_email_code_explanation`` — joined from email_validation_evidence.
- ``primary_email_quality_assessment`` — joined from email_validation_evidence.

The join uses the promoted ``primary_email`` value as the key; if a promoted
email has no row in the evidence CSV, the validation columns stay blank for
that record.
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import pandas as pd
import typer

app = typer.Typer(no_args_is_help=True)

DATASET_DEFAULT = Path("data/processed/family_offices_validated.csv")
EMAIL_EVIDENCE_DEFAULT = Path("data/processed/email_validation_evidence.csv")

DEFAULT_VALIDATION_PERIOD = "2026-05"

NEW_COLUMNS = (
    "data_validation_period",
    "family_office_domain",
    "url_quality",
    "primary_email_validation_code",
    "primary_email_code_explanation",
    "primary_email_quality_assessment",
)


def derive_domain(website_url: str) -> str:
    if not website_url:
        return ""
    netloc = urlparse(str(website_url)).netloc.lower().removeprefix("www.")
    return netloc


def derive_url_quality(website_ok: object, status_code: object) -> str:
    """Map (website_ok, status_code) -> categorical quality label."""
    try:
        code = int(float(status_code)) if status_code not in (None, "", "nan") else None
    except (TypeError, ValueError):
        code = None
    ok = str(website_ok).strip().lower() in {"true", "1", "yes"}
    if not ok:
        return "Failed"
    if code == 200:
        return "Highest"
    if code is not None and 200 < code < 300:
        return "High"
    if code is not None and 300 <= code < 400:
        return "Medium"
    if code is not None and 400 <= code < 500:
        return "Low"
    if code is None:
        return "Unknown"
    return "Failed"


def load_email_evidence_lookup(path: Path) -> dict[str, dict[str, str]]:
    """Map email (lowercased) -> validation columns."""
    if not path.exists():
        return {}
    df = pd.read_csv(path).fillna("")
    lookup: dict[str, dict[str, str]] = {}
    for row in df.to_dict(orient="records"):
        email_key = str(row.get("email", "")).strip().lower()
        if not email_key:
            continue
        lookup[email_key] = {
            "primary_email_validation_code": str(row.get("validation_code", "")),
            "primary_email_code_explanation": str(row.get("validation_explanation", "")),
            "primary_email_quality_assessment": str(row.get("email_quality_assessment", "")),
        }
    return lookup


def enrich_dataframe(
    df: pd.DataFrame,
    email_lookup: dict[str, dict[str, str]],
    validation_period: str = DEFAULT_VALIDATION_PERIOD,
) -> pd.DataFrame:
    df = df.copy()
    for column in NEW_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    for index, row in df.iterrows():
        df.at[index, "data_validation_period"] = validation_period
        df.at[index, "family_office_domain"] = derive_domain(str(row.get("website_url", "")))
        df.at[index, "url_quality"] = derive_url_quality(
            row.get("website_ok", False), row.get("website_status_code", "")
        )
        email = str(row.get("primary_email", "")).strip().lower()
        if email and email in email_lookup:
            for key, value in email_lookup[email].items():
                df.at[index, key] = value

    return df


@app.command("run")
def run_enrich(
    dataset: Annotated[Path, typer.Option("--dataset")] = DATASET_DEFAULT,
    email_evidence: Annotated[
        Path, typer.Option("--email-evidence")
    ] = EMAIL_EVIDENCE_DEFAULT,
    validation_period: Annotated[
        str, typer.Option("--validation-period")
    ] = DEFAULT_VALIDATION_PERIOD,
) -> None:
    """Add sample-workbook-parity columns to the validated CSV."""
    if not dataset.exists():
        raise typer.BadParameter(f"dataset not found: {dataset}")
    df = pd.read_csv(dataset).fillna("")
    email_lookup = load_email_evidence_lookup(email_evidence)
    new_df = enrich_dataframe(df, email_lookup, validation_period=validation_period)
    new_df.to_csv(dataset, index=False)

    populated = {
        column: int((new_df[column].astype(str) != "").sum())
        for column in NEW_COLUMNS
    }
    typer.echo(f"Enriched {len(new_df)} rows; populated counts per new column: {populated}")


if __name__ == "__main__":
    app()
