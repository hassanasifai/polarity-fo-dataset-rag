"""Promote social-media handles into the validated dataset.

Reads the Apify ``contact-info-scraper`` raw export (which captures every
social-platform link the scraper found on the FO's website) and writes one
URL column per platform plus a single ``social_media_evidence_url`` +
``social_media_confidence`` pair (the FO website URL is the discovery source).

Promotion rules:
- Only URLs whose host is on the expected platform's canonical domain are kept.
- Each platform value is paired with ``social_media_evidence_url`` set to the
  scraper's start URL (i.e. the FO website that the scraper crawled).
- Existing non-empty cells are never overwritten.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import pandas as pd
import typer

app = typer.Typer(no_args_is_help=True)

CONTACT_RAW_PATH_DEFAULT = Path(
    "data/evidence/raw_apify_exports/2026-05-17/"
    "contact_info_official_websites_2026_05_17.csv"
)

# (column on dataset, key on raw row, set of acceptable host substrings)
PLATFORM_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("twitter_url", "twitters", ("twitter.com", "x.com")),
    ("instagram_url", "instagrams", ("instagram.com",)),
    ("facebook_url", "facebooks", ("facebook.com", "fb.com")),
    ("youtube_url", "youtubes", ("youtube.com", "youtu.be")),
    ("tiktok_url", "tiktoks", ("tiktok.com",)),
)

EVIDENCE_COLUMN = "social_media_evidence_url"
CONFIDENCE_COLUMN = "social_media_confidence"
CONFIDENCE_VALUE = "linked_from_official_site"

PLATFORM_COLUMNS = tuple(col for col, _, _ in PLATFORM_RULES)
PROMOTED_COLUMNS = PLATFORM_COLUMNS + (EVIDENCE_COLUMN, CONFIDENCE_COLUMN)


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


def _parse_url_list(value: object) -> list[str]:
    """Parse a stored list-literal like ``['https://x.com/foo']`` into URLs."""
    if _is_nullish(value):
        return []
    text = str(value).strip()
    if not text or text in {"[]", "''", '""'}:
        return []
    try:
        parsed = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return [text] if text.startswith("http") else []
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    if isinstance(parsed, str) and parsed:
        return [parsed]
    return []


def _first_url_on_platform(urls: list[str], host_substrings: tuple[str, ...]) -> str | None:
    for url in urls:
        host = _domain(url)
        if any(sub in host for sub in host_substrings):
            return url
    return None


def load_contact_lookup(path: Path) -> dict[str, dict]:
    """Build domain → row lookup from the raw Apify contact-scraper export."""
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    lookup: dict[str, dict] = {}
    for row in df.to_dict(orient="records"):
        domain = _domain(row.get("originalStartUrl") or row.get("domain"))
        if domain:
            lookup.setdefault(domain, row)
    return lookup


def promote_row(record: dict, contact_row: dict | None) -> dict:
    if contact_row is None:
        return {}
    record_domain = _domain(record.get("website_url", ""))
    contact_domain = _domain(
        contact_row.get("originalStartUrl") or contact_row.get("domain")
    )
    if not record_domain or record_domain != contact_domain:
        return {}

    evidence_url = (
        str(contact_row.get("originalStartUrl") or "").strip()
        or str(record.get("website_url") or "").strip()
    )
    if not evidence_url:
        return {}

    updates: dict[str, str] = {}
    for column, raw_key, host_subs in PLATFORM_RULES:
        existing = record.get(column, "")
        if _is_nullish(existing):
            existing = ""
        if str(existing).strip():
            continue
        urls = _parse_url_list(contact_row.get(raw_key))
        match = _first_url_on_platform(urls, host_subs)
        if match:
            updates[column] = match

    if updates:
        updates[EVIDENCE_COLUMN] = evidence_url
        updates[CONFIDENCE_COLUMN] = CONFIDENCE_VALUE
    return updates


@app.command("run")
def run_promotion(
    dataset: Annotated[Path, typer.Option("--dataset")] = Path(
        "data/processed/family_offices_validated.csv"
    ),
    contact_raw: Annotated[
        Path, typer.Option("--contact-raw")
    ] = CONTACT_RAW_PATH_DEFAULT,
    json_output: Annotated[Path | None, typer.Option("--json-output")] = Path(
        "data/processed/family_offices_validated.json"
    ),
) -> None:
    """Promote per-platform social-media handles into the validated dataset."""
    if not dataset.exists():
        raise typer.BadParameter(f"dataset not found: {dataset}")
    df = pd.read_csv(dataset).fillna("")
    lookup = load_contact_lookup(contact_raw)

    for column in PROMOTED_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    counts: dict[str, int] = {column: 0 for column in PLATFORM_COLUMNS}
    promoted_rows = 0
    for index, row in df.iterrows():
        domain = _domain(row.get("website_url", ""))
        updates = promote_row(row.to_dict(), lookup.get(domain))
        if not updates:
            continue
        for column, value in updates.items():
            df.at[index, column] = value
        for column in PLATFORM_COLUMNS:
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
        f"Promoted social-media handles for {promoted_rows}/{len(df)} rows. "
        f"Field counts: {summary}."
    )


if __name__ == "__main__":
    app()
