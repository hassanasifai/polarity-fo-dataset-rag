"""Pass 4 — Filter Google News evidence and populate ``recent_activity``.

Filtering rules (deliberately conservative):

- Drop rows where the news scraper returned ``error=True``.
- Require ``pubDate >= 2025-01-01``.
- Require the FO name (or its non-stopword tokens) to appear in the title.
- Reject items whose ``sourceName`` matches a directory/aggregator block list.
- For each FO, keep the single most-recent surviving item.

Side effect: for records with zero surviving signals, append a `"no recent public
signal as of <today>"` note to ``uncertainty_notes`` (only if no such note is
already present).
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

app = typer.Typer(no_args_is_help=True)

NEWS_PATH_DEFAULT = Path("data/processed/google_news_recent_signals.csv")
DATASET_PATH_DEFAULT = Path("data/processed/family_offices_validated.csv")
JSON_PATH_DEFAULT = Path("data/processed/family_offices_validated.json")

DATE_FLOOR = pd.Timestamp("2025-01-01", tz="UTC")
BLOCKED_SOURCE_DOMAINS = {
    "pitchbook.com",
    "crunchbase.com",
    "zoominfo.com",
    "swfinstitute.org",
    "dev.swfinstitute.org",
    "wikipedia.org",
}
NAME_NOISE_RE = re.compile(r"[^a-z0-9]+")
NAME_STOPWORDS = {
    "family", "office", "the", "and", "co", "company", "group",
    "capital", "partners", "advisors", "advisory", "management",
    "wealth", "investment", "investments", "ag", "llc", "ltd", "lp",
    "inc", "plc", "trust", "&",
}


def _name_tokens(name: str) -> set[str]:
    cleaned = NAME_NOISE_RE.sub(" ", str(name or "").casefold()).strip()
    strict = {
        token for token in cleaned.split()
        if token and token not in NAME_STOPWORDS and len(token) > 2
    }
    if strict:
        return strict
    # Fallback for short or stopword-only names (e.g. "CM Wealth", "AT Capital Group"):
    # keep any non-stopword token of length ≥ 2.
    return {
        token for token in cleaned.split()
        if token and token not in NAME_STOPWORDS and len(token) >= 2
    }


def _normalize_text(text: str) -> str:
    return NAME_NOISE_RE.sub(" ", str(text or "").casefold())


def title_matches_name(title: str, fo_name: str) -> bool:
    tokens = _name_tokens(fo_name)
    if not tokens:
        return False
    normalized = _normalize_text(title)
    return all(token in normalized for token in tokens)


def is_blocked_source(source_name: str) -> bool:
    if not source_name:
        return False
    lowered = str(source_name).lower()
    return any(blocked in lowered for blocked in BLOCKED_SOURCE_DOMAINS)


def select_signal(
    news_df: pd.DataFrame,
    fo_name: str,
) -> dict | None:
    """Return the most-recent surviving signal for ``fo_name`` or None."""
    fo_rows = news_df[news_df["family_office_name"] == fo_name].copy()
    if fo_rows.empty:
        return None
    fo_rows = fo_rows[fo_rows["error"].isna() | (fo_rows["error"] != True)]  # noqa: E712
    if fo_rows.empty:
        return None
    fo_rows = fo_rows.dropna(subset=["title", "pubDate"])
    if fo_rows.empty:
        return None
    fo_rows["pub_dt"] = pd.to_datetime(fo_rows["pubDate"], errors="coerce", utc=True)
    fo_rows = fo_rows[fo_rows["pub_dt"].notna() & (fo_rows["pub_dt"] >= DATE_FLOOR)]
    if fo_rows.empty:
        return None
    fo_rows = fo_rows[~fo_rows["sourceName"].apply(is_blocked_source)]
    if fo_rows.empty:
        return None
    fo_rows = fo_rows[fo_rows["title"].apply(lambda t: title_matches_name(t, fo_name))]
    if fo_rows.empty:
        return None
    fo_rows = fo_rows.sort_values("pub_dt", ascending=False)
    top = fo_rows.iloc[0]
    return {
        "title": str(top["title"]).strip(),
        "url": str(top.get("articleUrl") or top.get("link") or "").strip(),
        "source_name": str(top.get("sourceName") or "").strip(),
        "pub_date": top["pub_dt"].date().isoformat(),
    }


def format_recent_activity(signal: dict) -> str:
    date_part = signal["pub_date"]
    source_part = signal["source_name"] or "news"
    url_part = signal["url"]
    base = f"{signal['title']} ({source_part}, {date_part})"
    if url_part:
        return f"{base} — {url_part}"
    return base


@app.command("run")
def run_news_promotion(
    dataset: Annotated[Path, typer.Option("--dataset")] = DATASET_PATH_DEFAULT,
    news: Annotated[Path, typer.Option("--news")] = NEWS_PATH_DEFAULT,
    json_output: Annotated[Path | None, typer.Option("--json-output")] = JSON_PATH_DEFAULT,
) -> None:
    """Filter news signals and populate recent_activity for matching records."""
    if not dataset.exists():
        raise typer.BadParameter(f"dataset not found: {dataset}")
    if not news.exists():
        raise typer.BadParameter(f"news evidence not found: {news}")

    df = pd.read_csv(dataset).fillna("")
    news_df = pd.read_csv(news)

    today = datetime.now(UTC).date().isoformat()
    promoted = 0
    no_signal = 0

    stale_note_re = re.compile(r"\s*;?\s*no recent public signal as of \d{4}-\d{2}-\d{2}")
    for index, row in df.iterrows():
        if row["recent_activity"]:
            continue
        signal = select_signal(news_df, row["family_office_name"])
        if signal is None:
            no_signal += 1
            uncertainty_note = f"no recent public signal as of {today}"
            current = str(row.get("uncertainty_notes") or "")
            if uncertainty_note not in current:
                df.at[index, "uncertainty_notes"] = (
                    f"{current}; {uncertainty_note}" if current else uncertainty_note
                )
            continue
        df.at[index, "recent_activity"] = format_recent_activity(signal)
        # Remove any stale "no recent public signal" note that an earlier run added.
        cleaned = stale_note_re.sub("", str(row.get("uncertainty_notes") or "")).strip(" ;")
        df.at[index, "uncertainty_notes"] = cleaned
        promoted += 1

    df.to_csv(dataset, index=False)
    if json_output is not None:
        json_output.write_text(
            json.dumps(df.to_dict(orient="records"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    typer.echo(
        f"Recent activity: promoted={promoted}, no_signal={no_signal} "
        f"(of {len(df)} records)"
    )


if __name__ == "__main__":
    app()
