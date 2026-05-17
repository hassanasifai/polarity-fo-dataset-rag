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
    "team_rosters_raw.csv": "team_rosters_raw",
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

BASE_DEFINITIONS = {
    "record_id": "Stable internal identifier for the family-office record.",
    "family_office_name": "Canonical public name of the family-office entity.",
    "family_office_type": (
        "Explicit classification; not all rows are classic single-family offices."
    ),
    "description": "Evidence-backed entity summary written from public sources.",
    "investment_thesis": "Observed or source-supported investment mandate / strategy summary.",
    "investing_sectors": "Observed sectors, asset classes, or mandate areas.",
    "aum_text": "AUM or client-asset language only when source text supports it; never inferred.",
    "website_url": "Official website used as the primary entity anchor.",
    "corporate_linkedin_url": "LinkedIn company page for the FO, when source-supported.",
    "street_address": (
        "Promoted address from domain-matched Google Places or LinkedIn company evidence."
    ),
    "city": "Headquarters city from official or corroborated source.",
    "state_region": "Headquarters state or region where available.",
    "country": "Headquarters country.",
    "principal_name": (
        "Legacy principal / founder / controlling-family field from the seed validation pass."
    ),
    "principal_title": "Legacy role/title paired with principal_name where available.",
    "principal_linkedin_url": (
        "Legacy principal LinkedIn field; intentionally blank unless directly verified."
    ),
    "primary_email": "Promoted corporate/public email, not SMTP inbox proof.",
    "primary_phone": "Promoted corporate/public phone number.",
    "recent_activity": (
        "Most recent qualifying public activity signal or regulatory/news statement."
    ),
    "source_urls": "List of public evidence URLs checked during validation.",
    "source_notes": "Human-readable source notes explaining why the record was accepted.",
    "extraction_method": "How the original row was researched or extracted.",
    "evidence_quality": "Source quality tier assigned during validation.",
    "uncertainty_notes": "Human-readable caveats preserving uncertainty instead of hiding it.",
    "source_count": "Number of source URLs attached to the record.",
    "validation_score": "Completeness and source-quality score from 0 to 100.",
    "confidence": "High/medium/low confidence derived from score and validation gates.",
    "validation_status": "Accepted/rejected status from deterministic validation.",
    "validation_notes": "Validation logic summary for the row.",
    "website_ok": "Whether the official website was reachable during validation.",
    "website_status_code": "HTTP status code from official website validation.",
    "website_final_url": "Final URL after redirects during validation.",
    "sources_ok": "Count of reachable source URLs.",
    "human_audit_status": "Reviewer verdict per row after manual audit.",
    "auto_prescreen_flag": "Advisory heuristic flag: looks_clean or look_carefully.",
    "auto_prescreen_reason": "Heuristic codes that fired during pre-screen.",
    "data_validation_period": "Validation cycle identifier (year-month) for this dataset snapshot.",
    "family_office_domain": "Bare website domain derived from website_url.",
    "url_quality": "Categorical website quality derived from reachability and status code.",
    "data_completion_score_text": (
        "Count of populated sample-facing fields using the sample denominator."
    ),
    "data_completion_score_visual": "Bar visualization of the sample-facing completion score.",
    "recent_activity_age_days": (
        "Days between recent_activity_date and the 2026-05-18 submission review date."
    ),
    "recent_activity_recency_label": "Derived recency bucket: fresh, moderate, or stale.",
    "primary_email_smtp_verified": (
        "False for promoted corporate emails; SMTP inbox verification was not performed."
    ),
    "primary_phone_conflict_with_places": (
        "True when the promoted primary phone disagrees with domain-matched Google Places."
    ),
    "primary_phone_canonical_source": (
        "Human-readable source preference used when phone evidence conflicts."
    ),
    "sec_form_adv_evidence_path": (
        "Public SEC PDF URL used as evidence for the parsed Form ADV fields."
    ),
}


def _definition_for_column(column_name: str) -> str:
    if column_name in BASE_DEFINITIONS:
        return BASE_DEFINITIONS[column_name]
    if column_name.endswith("_evidence_url"):
        return "Source URL supporting the paired promoted field."
    if column_name.endswith("_confidence"):
        return "Confidence label describing the evidence path for the paired promoted field."
    if column_name.startswith("linkedin_"):
        return "LinkedIn company-page enrichment joined only by matching FO website domain."
    if column_name in {"twitter_url", "instagram_url", "facebook_url", "youtube_url", "tiktok_url"}:
        return "Social-media URL discovered from the FO's official website crawl."
    if column_name.startswith("google_places_") or column_name == "google_maps_url":
        return (
            "Google Places corroboration retained only when returned website domain "
            "matched the FO."
        )
    if column_name.startswith("sec_") or column_name.startswith("form_adv_"):
        return "SEC IAPD / Form ADV regulatory identifier or disclosure link."
    if column_name.endswith("_linkedin_url"):
        return "Principal LinkedIn URL only when linked from an official profile page."
    if column_name.endswith("_linkedin_confidence"):
        return "Confidence label for the paired principal LinkedIn URL."
    if column_name.startswith("principal_") and "_" in column_name:
        return "Multi-principal slot promoted from official team/about-page evidence."
    if column_name.startswith("contact_"):
        return "Sample-workbook parity contact field derived only from validated public data."
    if "secondary" in column_name:
        return (
            "Sample-workbook parity secondary-contact field; blank or marked no "
            "evidence unless sourced."
        )
    if column_name.startswith("primary_email_"):
        return "Primary corporate email validation or evidence metadata."
    if column_name.startswith("primary_phone_"):
        return "Primary corporate phone evidence or corroboration metadata."
    if column_name.startswith("recent_activity_"):
        return "Structured metadata for the recent_activity signal."
    if column_name.startswith("street_address_"):
        return "Street-address evidence metadata."
    return "Dataset column retained for auditability; see methodology_summary.md for context."


def _data_dictionary_rows(data_columns: list[str]) -> list[dict[str, str]]:
    return [
        {"column_name": column, "definition": _definition_for_column(column)}
        for column in data_columns
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

    data_df = pd.read_csv(csv_path, dtype=str).fillna("")

    with pd.ExcelWriter(xlsx_output, engine="openpyxl") as writer:
        data_df.to_excel(writer, sheet_name="data_50", index=False)
        pd.DataFrame(_data_dictionary_rows(list(data_df.columns))).to_excel(
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
