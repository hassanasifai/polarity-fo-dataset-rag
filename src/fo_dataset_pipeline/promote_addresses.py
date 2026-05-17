"""Promote ``street_address`` for FOs where evidence sources have it.

The seed dataset left ``street_address`` blank for all 50 records. We have it
in two evidence sources already on disk:

1. Google Places (domain-verified) — strongest signal, written first.
2. LinkedIn company enrichment — fallback when Places didn't match.

Both sources are joined by FO domain (already the matching key for our
existing promoters). Every write is paired with an evidence URL and
confidence label.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import pandas as pd
import typer

app = typer.Typer(no_args_is_help=True)

DEFAULT_DATASET = Path("data/processed/family_offices_validated.csv")
DEFAULT_LINKEDIN_EVIDENCE = Path("data/processed/linkedin_company_evidence.csv")
DEFAULT_PLACES_EVIDENCE = Path("data/processed/google_places_evidence.csv")
DEFAULT_JSON_OUTPUT = Path("data/processed/family_offices_validated.json")

EVIDENCE_COLUMN = "street_address_evidence_url"
CONFIDENCE_COLUMN = "street_address_confidence"


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
    if not text or "://" not in text:
        if text and "." in text:
            text = "http://" + text
        else:
            return ""
    return urlparse(text).netloc.lower().removeprefix("www.")


def _load_places_streets(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    df = pd.read_csv(path).fillna("")
    out: dict[str, dict] = {}
    for row in df.to_dict(orient="records"):
        if str(row.get("temporarily_closed")).lower() == "true":
            continue
        if str(row.get("permanently_closed")).lower() == "true":
            continue
        domain = _domain(row.get("website"))
        street = str(row.get("street") or "").strip()
        if not domain or not street:
            continue
        out.setdefault(
            domain,
            {
                "street": street,
                "evidence_url": str(row.get("url") or "").strip(),
            },
        )
    return out


def _load_linkedin_streets(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    df = pd.read_csv(path).fillna("")
    out: dict[str, dict] = {}
    for row in df.to_dict(orient="records"):
        domain = _domain(row.get("website"))
        street = str(row.get("street") or "").strip()
        linkedin_url = str(row.get("linkedinUrl") or "").strip()
        if not domain or not street or "linkedin.com/company/" not in linkedin_url.lower():
            continue
        out.setdefault(domain, {"street": street, "evidence_url": linkedin_url})
    return out


def promote_row(record: dict, places: dict | None, linkedin: dict | None) -> dict:
    existing = record.get("street_address")
    if not _is_nullish(existing) and str(existing).strip():
        return {}
    updates: dict[str, str] = {}
    if places and places.get("street"):
        updates["street_address"] = places["street"]
        updates[EVIDENCE_COLUMN] = places["evidence_url"]
        updates[CONFIDENCE_COLUMN] = "google_places_domain_match"
        return updates
    if linkedin and linkedin.get("street"):
        updates["street_address"] = linkedin["street"]
        updates[EVIDENCE_COLUMN] = linkedin["evidence_url"]
        updates[CONFIDENCE_COLUMN] = "linkedin_company_page"
    return updates


@app.command("run")
def run_promotion(
    dataset: Annotated[Path, typer.Option("--dataset")] = DEFAULT_DATASET,
    places_evidence: Annotated[
        Path, typer.Option("--places-evidence")
    ] = DEFAULT_PLACES_EVIDENCE,
    linkedin_evidence: Annotated[
        Path, typer.Option("--linkedin-evidence")
    ] = DEFAULT_LINKEDIN_EVIDENCE,
    json_output: Annotated[Path | None, typer.Option("--json-output")] = DEFAULT_JSON_OUTPUT,
) -> None:
    if not dataset.exists():
        raise typer.BadParameter(f"dataset not found: {dataset}")
    df = pd.read_csv(dataset).fillna("")
    places_lookup = _load_places_streets(places_evidence)
    linkedin_lookup = _load_linkedin_streets(linkedin_evidence)

    for column in ("street_address", EVIDENCE_COLUMN, CONFIDENCE_COLUMN):
        if column not in df.columns:
            df[column] = ""

    promoted_places = 0
    promoted_linkedin = 0
    for index, row in df.iterrows():
        domain = _domain(row.get("website_url", ""))
        updates = promote_row(
            row.to_dict(),
            places_lookup.get(domain),
            linkedin_lookup.get(domain),
        )
        if not updates:
            continue
        for column, value in updates.items():
            df.at[index, column] = value
        if updates.get(CONFIDENCE_COLUMN) == "google_places_domain_match":
            promoted_places += 1
        elif updates.get(CONFIDENCE_COLUMN) == "linkedin_company_page":
            promoted_linkedin += 1

    df.to_csv(dataset, index=False)
    if json_output is not None:
        json_output.write_text(
            json.dumps(df.to_dict(orient="records"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    typer.echo(
        f"Street-address promoted: places={promoted_places}, "
        f"linkedin_fallback={promoted_linkedin}."
    )


if __name__ == "__main__":
    app()
