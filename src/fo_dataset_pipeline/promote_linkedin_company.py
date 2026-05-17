"""Promote LinkedIn company-page enrichment fields into the validated dataset.

Reads ``data/processed/linkedin_company_evidence.csv`` (Apify LinkedIn company
scraper output) and promotes 7 corporate-level enrichment fields per row:
employee count, follower count, specialties, size band, industry, founded year,
and full headquarters string.

Promotion rules (HVL-aligned):

- Only LinkedIn URLs that match ``linkedin.com/company/`` are accepted (school
  pages and personal profiles are rejected).
- The website domain on the LinkedIn record must match the family-office domain
  on the dataset row. No cross-domain promotion.
- Every promoted value carries ``_evidence_url`` = the LinkedIn company page URL
  and ``_confidence`` = ``linkedin_company_page``.
- Existing non-empty cells are never overwritten.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import pandas as pd
import typer

app = typer.Typer(no_args_is_help=True)

COMPANY_LINKEDIN_RE = re.compile(r"linkedin\.com/company/", re.IGNORECASE)

LINKEDIN_EVIDENCE_PATH = Path("data/processed/linkedin_company_evidence.csv")

PROMOTED_VALUE_COLUMNS = (
    "linkedin_employee_count",
    "linkedin_follower_count",
    "linkedin_specialties",
    "linkedin_company_size_band",
    "linkedin_industry",
    "linkedin_founded_year",
    "linkedin_headquarters_full",
)

EVIDENCE_COLUMN = "linkedin_company_evidence_url"
CONFIDENCE_COLUMN = "linkedin_company_confidence"
CONFIDENCE_VALUE = "linkedin_company_page"

PROMOTED_COLUMNS = PROMOTED_VALUE_COLUMNS + (EVIDENCE_COLUMN, CONFIDENCE_COLUMN)


def _is_nullish(value: object) -> bool:
    """True for None, pd.NA, np.nan, or any pandas-null scalar."""
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


def _format_specialties(value: object) -> str:
    """Render the LinkedIn ``specialties`` value as a semicolon-joined string."""
    if _is_nullish(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            parsed = None
        if isinstance(parsed, list):
            return "; ".join(str(item).strip() for item in parsed if str(item).strip())
    return text


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


def _format_headquarters(row: dict) -> str:
    parts: list[str] = []
    for key in ("street", "city", "state", "country", "postalCode"):
        raw = row.get(key)
        if _is_nullish(raw):
            continue
        text = str(raw).strip()
        if text and text.lower() != "nan":
            parts.append(text)
    return ", ".join(parts)


def load_linkedin_lookup(path: Path) -> dict[str, dict]:
    """Build domain → row lookup, keeping only rows with a company LinkedIn URL."""
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    lookup: dict[str, dict] = {}
    for row in df.to_dict(orient="records"):
        website_domain = _domain(row.get("website", ""))
        linkedin_url = str(row.get("linkedinUrl") or "").strip()
        if not website_domain or not linkedin_url:
            continue
        if not COMPANY_LINKEDIN_RE.search(linkedin_url):
            continue
        # Prefer the first matching row per domain (rows are emitted in scraper order).
        lookup.setdefault(website_domain, row)
    return lookup


def promote_row(record: dict, linkedin_row: dict | None) -> dict:
    """Return cells to write for one dataset row."""
    if linkedin_row is None:
        return {}
    linkedin_url = str(linkedin_row.get("linkedinUrl") or "").strip()
    if not linkedin_url or not COMPANY_LINKEDIN_RE.search(linkedin_url):
        return {}

    record_domain = _domain(record.get("website_url", ""))
    li_domain = _domain(linkedin_row.get("website", ""))
    if not record_domain or record_domain != li_domain:
        return {}

    candidates = {
        "linkedin_employee_count": _format_int(linkedin_row.get("employeeCount")),
        "linkedin_follower_count": _format_int(linkedin_row.get("followerCount")),
        "linkedin_specialties": _format_specialties(linkedin_row.get("specialties")),
        "linkedin_company_size_band": str(linkedin_row.get("companySize") or "").strip(),
        "linkedin_industry": str(linkedin_row.get("industry") or "").strip(),
        "linkedin_founded_year": _format_int(linkedin_row.get("foundedYear")),
        "linkedin_headquarters_full": _format_headquarters(linkedin_row),
    }

    updates: dict[str, str] = {}
    for column, new_value in candidates.items():
        if not new_value:
            continue
        existing = record.get(column, "")
        if _is_nullish(existing):
            existing = ""
        if str(existing).strip():
            continue  # never overwrite an existing non-empty cell
        updates[column] = new_value

    if updates:
        updates[EVIDENCE_COLUMN] = linkedin_url
        updates[CONFIDENCE_COLUMN] = CONFIDENCE_VALUE
    return updates


@app.command("run")
def run_promotion(
    dataset: Annotated[Path, typer.Option("--dataset")] = Path(
        "data/processed/family_offices_validated.csv"
    ),
    linkedin_evidence: Annotated[
        Path, typer.Option("--linkedin-evidence")
    ] = LINKEDIN_EVIDENCE_PATH,
    json_output: Annotated[Path | None, typer.Option("--json-output")] = Path(
        "data/processed/family_offices_validated.json"
    ),
) -> None:
    """Promote LinkedIn company-page enrichment fields into the validated dataset."""
    if not dataset.exists():
        raise typer.BadParameter(f"dataset not found: {dataset}")
    df = pd.read_csv(dataset).fillna("")
    linkedin_lookup = load_linkedin_lookup(linkedin_evidence)

    for column in PROMOTED_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    counts: dict[str, int] = {column: 0 for column in PROMOTED_VALUE_COLUMNS}
    promoted_rows = 0
    for index, row in df.iterrows():
        domain = _domain(row.get("website_url", ""))
        updates = promote_row(row.to_dict(), linkedin_lookup.get(domain))
        if not updates:
            continue
        for column, value in updates.items():
            df.at[index, column] = value
        for column in PROMOTED_VALUE_COLUMNS:
            if column in updates:
                counts[column] += 1
        promoted_rows += 1

    df.to_csv(dataset, index=False)

    if json_output is not None:
        json_output.write_text(
            json.dumps(df.to_dict(orient="records"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    summary = ", ".join(f"{name}={count}" for name, count in counts.items())
    typer.echo(
        f"Promoted LinkedIn enrichment for {promoted_rows}/{len(df)} rows. "
        f"Field counts: {summary}."
    )


if __name__ == "__main__":
    app()
