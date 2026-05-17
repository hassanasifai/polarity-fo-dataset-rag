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

from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import pandas as pd
import typer

app = typer.Typer(no_args_is_help=True)

DATASET_DEFAULT = Path("data/processed/family_offices_validated.csv")
EMAIL_EVIDENCE_DEFAULT = Path("data/processed/email_validation_evidence.csv")

DEFAULT_VALIDATION_PERIOD = "2026-05"
RECENCY_AS_OF_DATE = date(2026, 5, 18)

NEW_COLUMNS = (
    "data_validation_period",
    "family_office_domain",
    "url_quality",
    "primary_email_validation_code",
    "primary_email_code_explanation",
    "primary_email_quality_assessment",
    # Sample-parity derivations added in the workstream-F polish pass.
    "contact_first_name",
    "contact_last_name",
    "contact_full_name",
    "contact_location",
    "contact_secondary_email",
    "secondary_email_validation_code",
    "email_code_explanation_secondary",
    "email_quality_assessment_secondary",
    "contact_secondary_phone",
    "recent_activity_age_days",
    "recent_activity_recency_label",
    "primary_email_smtp_verified",
    "primary_phone_conflict_with_places",
    "primary_phone_canonical_source",
)

SECONDARY_CONTACT_UNCERTAINTY_NOTE = (
    "No secondary channel surfaced in the evidence layer; left null rather "
    "than fabricated."
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


def split_principal_name(full_name: str) -> tuple[str, str]:
    """Return (first_name, last_name) from a freeform principal-name string.

    Conservative: if the input is empty, a generic placeholder ("Dekker
    family", "Founders", etc.) or only one token, both outputs are empty.
    """
    if not full_name:
        return "", ""
    cleaned = full_name.strip()
    if not cleaned:
        return "", ""
    # Reject obvious placeholders / collective references.
    lowered = cleaned.lower()
    placeholders = {
        "family", "founders", "principals", "principal family",
        "founding family", "members",
    }
    if any(token == lowered or token in lowered.split() for token in placeholders):
        if any(lowered.endswith(suffix) for suffix in (" family", " family.")):
            return "", ""
    tokens = cleaned.split()
    if len(tokens) < 2:
        return "", ""
    # Drop trailing suffixes like "Jr.", "Sr.", "III" from the last token if present.
    suffixes = {"jr.", "jr", "sr.", "sr", "ii", "iii", "iv"}
    if tokens[-1].lower() in suffixes and len(tokens) >= 3:
        last_name = tokens[-2]
        first_name = " ".join(tokens[:-2])
    else:
        last_name = tokens[-1]
        first_name = " ".join(tokens[:-1])
    return first_name.strip(), last_name.strip()


def derive_contact_location(city: object, state: object, country: object) -> str:
    parts = [
        str(value).strip()
        for value in (city, state, country)
        if value is not None and str(value).strip() and str(value).strip().lower() != "nan"
    ]
    return ", ".join(parts)


def derive_recent_activity_age_days(activity_date: object) -> str:
    text = str(activity_date or "").strip()
    if not text or text.lower() == "nan":
        return ""
    try:
        parsed = date.fromisoformat(text[:10])
    except ValueError:
        return ""
    return str(max((RECENCY_AS_OF_DATE - parsed).days, 0))


def derive_recent_activity_recency_label(age_days: str) -> str:
    if not age_days:
        return ""
    age = int(age_days)
    if age <= 90:
        return "fresh"
    if age <= 365:
        return "moderate"
    return "stale"


def _append_note(existing: object, note: str) -> str:
    text = str(existing or "").strip()
    if note in text:
        return text
    if not text:
        return note
    return f"{text} {note}"


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


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

        # Sample-parity derivations (do not overwrite existing values).
        principal_name = str(row.get("principal_name", "")).strip()
        first_name, last_name = split_principal_name(principal_name)
        if first_name and not str(row.get("contact_first_name") or "").strip():
            df.at[index, "contact_first_name"] = first_name
        if last_name and not str(row.get("contact_last_name") or "").strip():
            df.at[index, "contact_last_name"] = last_name
        if principal_name and not str(row.get("contact_full_name") or "").strip():
            df.at[index, "contact_full_name"] = principal_name

        location = derive_contact_location(
            row.get("city"), row.get("state_region"), row.get("country")
        )
        if location and not str(row.get("contact_location") or "").strip():
            df.at[index, "contact_location"] = location

        # Secondary contact channels — explicit "absent by design" sentinels in
        # the validation columns; values are honest nulls.
        if not str(row.get("secondary_email_validation_code") or "").strip():
            df.at[index, "secondary_email_validation_code"] = "no_secondary_evidence"
        if not str(row.get("email_code_explanation_secondary") or "").strip():
            df.at[index, "email_code_explanation_secondary"] = (
                SECONDARY_CONTACT_UNCERTAINTY_NOTE
            )
        if not str(row.get("email_quality_assessment_secondary") or "").strip():
            df.at[index, "email_quality_assessment_secondary"] = "no_secondary_evidence"

        age_days = derive_recent_activity_age_days(row.get("recent_activity_date"))
        if age_days:
            df.at[index, "recent_activity_age_days"] = age_days
            recency_label = derive_recent_activity_recency_label(age_days)
            df.at[index, "recent_activity_recency_label"] = recency_label
            if recency_label == "stale":
                df.at[index, "uncertainty_notes"] = _append_note(
                    row.get("uncertainty_notes"),
                    "Recent-activity signal is older than 365 days as of 2026-05-18.",
                )

        if email:
            df.at[index, "primary_email_smtp_verified"] = "False"

        places_status = _cell_text(row.get("primary_phone_corroborated_by_places"))
        if places_status == "False":
            df.at[index, "primary_phone_conflict_with_places"] = "True"
            df.at[index, "primary_phone_canonical_source"] = (
                "official_or_scraped_contact_source_preferred_over_places"
            )
            df.at[index, "uncertainty_notes"] = _append_note(
                df.at[index, "uncertainty_notes"],
                "Primary phone conflicts with domain-matched Google Places; "
                "website/contact-source value retained as canonical.",
            )
        elif places_status == "True":
            df.at[index, "primary_phone_conflict_with_places"] = "False"
            df.at[index, "primary_phone_canonical_source"] = (
                "official_or_scraped_contact_source_corroborated_by_places"
            )
        elif str(row.get("primary_phone") or "").strip():
            df.at[index, "primary_phone_canonical_source"] = (
                "official_or_scraped_contact_source"
            )

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
