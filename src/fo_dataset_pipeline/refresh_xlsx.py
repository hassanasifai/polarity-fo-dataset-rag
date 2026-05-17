"""Rebuild ``family_offices_validated.xlsx`` from the on-disk CSV outputs.

Used after Pass 2/3/4 enrichments mutate the validated CSV, so the XLSX
workbook reflects the latest dataset state (promoted contacts, recent activity,
audit columns, validation chain snippets) without rerunning ``cli validate``
(which would read from the seed CSV and wipe the enrichments).
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

app = typer.Typer(no_args_is_help=True)

PROCESSED_DIR_DEFAULT = Path("data/processed")
XLSX_DEFAULT = Path("data/processed/family_offices_validated.xlsx")

EVIDENCE_SHEETS = {
    "source_registry.csv": "sources",
    "field_evidence.csv": "field_evidence",
    "validation_results.csv": "validation_results",
    "validation_chain_snippets.csv": "validation_chain_snippets",
    "apify_crawl_evidence.csv": "apify_evidence",
    "firecrawl_crawl_evidence.csv": "firecrawl_evidence",
    "contact_info_evidence.csv": "contact_info_evidence",
    "email_validation_evidence.csv": "email_validation_evidence",
    "google_news_recent_signals.csv": "google_news_signals",
    "google_places_evidence.csv": "google_places_evidence",
    "linkedin_company_evidence.csv": "linkedin_company_evidence",
    "cheerio_homepage_evidence.csv": "cheerio_homepage",
    "playwright_homepage_evidence.csv": "playwright_homepage",
}


def _data_dictionary_rows() -> list[dict[str, str]]:
    return [
        {"column_name": "family_office_type",
         "definition": "Explicit classification; not all rows are classic single-family offices."},
        {"column_name": "source_urls",
         "definition": "List of public evidence URLs checked during live validation."},
        {"column_name": "validation_score",
         "definition": "Completeness and source-quality score from 0 to 100."},
        {"column_name": "confidence",
         "definition": "High/medium/low confidence derived from score and validation gates."},
        {"column_name": "uncertainty_notes",
         "definition": "Human-readable caveats preserving uncertainty instead of hiding it."},
        {"column_name": "human_audit_status",
         "definition": "Reviewer verdict per row: pending until a human walks the row."},
        {"column_name": "auto_prescreen_flag",
         "definition": "Advisory: look_carefully or looks_clean from deterministic heuristics."},
        {"column_name": "auto_prescreen_reason",
         "definition": "Heuristic codes that fired during pre-screen (advisory, not verdicts)."},
        {"column_name": "primary_email_evidence_url",
         "definition": "URL on which the promoted corporate email was first observed."},
        {"column_name": "primary_email_confidence",
         "definition": "corporate_public_listed | mx_only | unverified."},
        {"column_name": "primary_phone_evidence_url",
         "definition": "URL on which the promoted corporate phone was first observed."},
        {"column_name": "primary_phone_confidence",
         "definition": "corporate_public_listed | unverified."},
        {"column_name": "corporate_linkedin_evidence_url",
         "definition": "URL where the corporate LinkedIn link was found (LinkedIn or own site)."},
        {"column_name": "corporate_linkedin_confidence",
         "definition": "linkedin_scraped_match | linked_from_official_site."},
        {"column_name": "recent_activity",
         "definition": "Most recent qualifying public news signal (2025+) with source and date."},
        {"column_name": "data_validation_period",
         "definition": "Validation cycle identifier (year-month) for this dataset snapshot."},
        {"column_name": "family_office_domain",
         "definition": "Bare website domain (no scheme, no www) derived from website_url."},
        {"column_name": "url_quality",
         "definition": "Categorical website quality: Highest=200, High=2xx, Medium=3xx, "
                       "Low=4xx, Failed=unreachable."},
        {"column_name": "primary_email_validation_code",
         "definition": "Code from local DNS/MX validation (e.g. mx_ok_source_domain_match)."},
        {"column_name": "primary_email_code_explanation",
         "definition": "Human-readable explanation of the validation code; explicitly NOT "
                       "an SMTP inbox proof."},
        {"column_name": "primary_email_quality_assessment",
         "definition": "Categorical: good_public_domain_mx | risky_mx_only | unknown_no_mx."},
    ]


@app.command("run")
def rebuild_xlsx(
    processed_dir: Annotated[
        Path, typer.Option("--processed-dir")
    ] = PROCESSED_DIR_DEFAULT,
    xlsx_output: Annotated[Path, typer.Option("--xlsx-output")] = XLSX_DEFAULT,
) -> None:
    """Reassemble the validated XLSX from on-disk CSVs without re-validating."""
    csv_path = processed_dir / "family_offices_validated.csv"
    if not csv_path.exists():
        raise typer.BadParameter(f"validated CSV not found: {csv_path}")

    data_df = pd.read_csv(csv_path)

    with pd.ExcelWriter(xlsx_output, engine="openpyxl") as writer:
        data_df.to_excel(writer, sheet_name="data_50", index=False)
        pd.DataFrame(_data_dictionary_rows()).to_excel(
            writer, sheet_name="data_dictionary", index=False
        )
        for filename, sheet_name in EVIDENCE_SHEETS.items():
            path = processed_dir / filename
            if not path.exists():
                continue
            try:
                pd.read_csv(path).to_excel(writer, sheet_name=sheet_name, index=False)
            except pd.errors.EmptyDataError:
                continue

    typer.echo(f"Rebuilt XLSX at {xlsx_output} with {len(data_df)} dataset rows.")


if __name__ == "__main__":
    app()
