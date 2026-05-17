"""Promote Google Places corroboration fields into the validated dataset.

Reads ``data/processed/google_places_evidence.csv`` (Apify Google-Maps scraper
output). The scraper sometimes returns the wrong business for a search string
(e.g. "Ralph Family Office London" returned "Pall Mall Family Office Ltd"), so
we ONLY promote a row when the Places-returned ``website`` shares the same
bare domain as the FO's ``website_url``. This guarantees we are corroborating
the same entity, not a similarly named one.

Promoted columns:
- ``google_places_phone`` — phone number Google Maps lists for the business.
- ``google_places_reviews_count`` — public review count (an activity signal).
- ``google_places_rating`` — average rating out of 5.
- ``google_places_category`` — Google Maps category label.
- ``google_maps_url`` — direct link to the listing.
- ``primary_phone_corroborated_by_places`` — True/False/(empty) sidecar; True
  when the existing ``primary_phone`` matches Places phone, False when they
  disagree, empty when one side is missing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import pandas as pd
import typer

app = typer.Typer(no_args_is_help=True)

PLACES_EVIDENCE_PATH = Path("data/processed/google_places_evidence.csv")

PROMOTED_VALUE_COLUMNS = (
    "google_places_phone",
    "google_places_reviews_count",
    "google_places_rating",
    "google_places_category",
    "google_maps_url",
)
EVIDENCE_COLUMN = "google_places_evidence_url"
CONFIDENCE_COLUMN = "google_places_confidence"
CONFIDENCE_VALUE = "google_places_domain_match"
PHONE_CORROBORATION_COLUMN = "primary_phone_corroborated_by_places"

PROMOTED_COLUMNS = PROMOTED_VALUE_COLUMNS + (
    EVIDENCE_COLUMN,
    CONFIDENCE_COLUMN,
    PHONE_CORROBORATION_COLUMN,
)


def _is_nullish(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _domain(url: object) -> str:
    if _is_nullish(url):
        return ""
    text = str(url).strip()
    if not text:
        return ""
    if "://" not in text:
        text = "http://" + text
    netloc = urlparse(text).netloc.lower().removeprefix("www.")
    return netloc


def _format_int(value: object) -> str:
    if _is_nullish(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        return str(int(float(text)))
    except (ValueError, TypeError):
        return text


def _format_rating(value: object) -> str:
    if _is_nullish(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        return f"{float(text):.1f}"
    except (ValueError, TypeError):
        return text


def _digits_only(value: object) -> str:
    if _is_nullish(value):
        return ""
    return re.sub(r"\D", "", str(value))


def _phones_match(left: object, right: object) -> bool:
    left_digits = _digits_only(left)
    right_digits = _digits_only(right)
    if not left_digits or not right_digits:
        return False
    # Compare last 10 digits to ignore differing country codes / leading zeros.
    return left_digits[-10:] == right_digits[-10:]


def load_places_lookup(path: Path) -> dict[str, dict]:
    """Build domain → Places row lookup, keyed by the website Places returned."""
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    lookup: dict[str, dict] = {}
    for row in df.to_dict(orient="records"):
        # Reject closed listings as evidence.
        if str(row.get("temporarily_closed")).lower() == "true":
            continue
        if str(row.get("permanently_closed")).lower() == "true":
            continue
        place_domain = _domain(row.get("website"))
        if place_domain:
            lookup.setdefault(place_domain, row)
    return lookup


def _select_phone(row: dict) -> str:
    raw = row.get("phone")
    if not _is_nullish(raw) and str(raw).strip():
        return str(raw).strip()
    raw_unformatted = row.get("phone_unformatted")
    if not _is_nullish(raw_unformatted) and str(raw_unformatted).strip():
        return str(raw_unformatted).strip()
    return ""


def promote_row(record: dict, places_row: dict | None) -> dict:
    if places_row is None:
        return {}

    record_domain = _domain(record.get("website_url", ""))
    place_domain = _domain(places_row.get("website"))
    if not record_domain or record_domain != place_domain:
        return {}

    evidence_url = str(places_row.get("url") or "").strip()
    if not evidence_url:
        return {}

    candidates: dict[str, str] = {
        "google_places_phone": _select_phone(places_row),
        "google_places_reviews_count": _format_int(places_row.get("reviews_count")),
        "google_places_rating": _format_rating(places_row.get("total_score")),
        "google_places_category": str(places_row.get("category_name") or "").strip(),
        "google_maps_url": evidence_url,
    }

    updates: dict[str, str] = {}
    for column, new_value in candidates.items():
        if not new_value:
            continue
        existing = record.get(column, "")
        if _is_nullish(existing):
            existing = ""
        if str(existing).strip():
            continue
        updates[column] = new_value

    if updates:
        updates[EVIDENCE_COLUMN] = evidence_url
        updates[CONFIDENCE_COLUMN] = CONFIDENCE_VALUE

        # Sidecar phone-corroboration flag. Never modifies primary_phone_confidence.
        primary_phone = record.get("primary_phone", "")
        places_phone = candidates["google_places_phone"]
        if places_phone and not _is_nullish(primary_phone) and str(primary_phone).strip():
            updates[PHONE_CORROBORATION_COLUMN] = (
                "True" if _phones_match(primary_phone, places_phone) else "False"
            )

    return updates


@app.command("run")
def run_promotion(
    dataset: Annotated[Path, typer.Option("--dataset")] = Path(
        "data/processed/family_offices_validated.csv"
    ),
    places_evidence: Annotated[
        Path, typer.Option("--places-evidence")
    ] = PLACES_EVIDENCE_PATH,
    json_output: Annotated[Path | None, typer.Option("--json-output")] = Path(
        "data/processed/family_offices_validated.json"
    ),
) -> None:
    """Promote Google Places corroboration fields into the validated dataset."""
    if not dataset.exists():
        raise typer.BadParameter(f"dataset not found: {dataset}")
    df = pd.read_csv(dataset).fillna("")
    lookup = load_places_lookup(places_evidence)

    for column in PROMOTED_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    counts: dict[str, int] = {column: 0 for column in PROMOTED_VALUE_COLUMNS}
    promoted_rows = 0
    corroborated_phone = 0
    conflicting_phone = 0
    for index, row in df.iterrows():
        domain = _domain(row.get("website_url", ""))
        updates = promote_row(row.to_dict(), lookup.get(domain))
        if not updates:
            continue
        for column, value in updates.items():
            df.at[index, column] = value
        for column in PROMOTED_VALUE_COLUMNS:
            if column in updates:
                counts[column] += 1
        promoted_rows += 1
        if updates.get(PHONE_CORROBORATION_COLUMN) == "True":
            corroborated_phone += 1
        elif updates.get(PHONE_CORROBORATION_COLUMN) == "False":
            conflicting_phone += 1

    df.to_csv(dataset, index=False)

    if json_output is not None:
        json_output.write_text(
            json.dumps(df.to_dict(orient="records"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    summary = ", ".join(f"{name}={count}" for name, count in counts.items())
    typer.echo(
        f"Promoted Google Places for {promoted_rows}/{len(df)} rows. "
        f"Field counts: {summary}. "
        f"Primary-phone corroboration: matched={corroborated_phone}, "
        f"conflicted={conflicting_phone}."
    )


if __name__ == "__main__":
    app()
