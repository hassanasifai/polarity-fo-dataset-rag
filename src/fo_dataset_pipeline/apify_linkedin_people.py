"""Scrape LinkedIn company employees via the cookieless Apify actor.

Uses ``apimaestro/linkedin-company-employees-scraper-no-cookies`` (the most-run
cookieless variant on Apify Store, 534k+ runs as of 2026-05). For each FO with
a ``corporate_linkedin_url`` we request up to 15 employees, then store the raw
response under ``data/evidence/apify_linkedin_people_2026_05_17/<record_id>.json``.

Token handling:
- Reads ``APIFY_TOKEN`` from env first; if blank, tries ``APIFY_TOKEN_1``,
  ``APIFY_TOKEN_2``, ``APIFY_TOKEN_3`` and uses the first that authorizes.
- Tokens are never written to disk and never echoed in log lines.

The promoter (``promote_linkedin_principals``) is a separate module — this one
just produces evidence.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Annotated

import httpx
import pandas as pd
import typer

app = typer.Typer(no_args_is_help=True)

ACTOR_ID = "apimaestro~linkedin-company-employees-scraper-no-cookies"
DEFAULT_OUTPUT_DIR = Path("data/evidence/apify_linkedin_people_2026_05_17")
DEFAULT_DATASET = Path("data/processed/family_offices_validated.csv")
PRICE_PER_ITEM_USD = 0.01


def _resolve_token() -> str | None:
    for env_name in ("APIFY_TOKEN", "APIFY_TOKEN_1", "APIFY_TOKEN_2", "APIFY_TOKEN_3"):
        value = os.environ.get(env_name) or ""
        if value.strip():
            return value.strip()
    return None


def _verify_token(token: str) -> bool:
    response = httpx.get(
        "https://api.apify.com/v2/users/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15.0,
    )
    return response.status_code == 200


def _run_actor_for_company(
    client: httpx.Client,
    token: str,
    company_url: str,
    max_employees: int,
) -> list[dict]:
    response = client.post(
        f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "identifier": company_url,
            "max_employees": max_employees,
        },
        timeout=240.0,
    )
    if response.status_code >= 400:
        return [{"_error": True, "status": response.status_code, "body": response.text[:300]}]
    data = response.json()
    if not isinstance(data, list):
        return []
    return data


@app.command("run")
def run_scrape(
    dataset: Annotated[Path, typer.Option("--dataset")] = DEFAULT_DATASET,
    output_dir: Annotated[Path, typer.Option("--output-dir")] = DEFAULT_OUTPUT_DIR,
    max_employees: Annotated[int, typer.Option("--max-employees")] = 15,
    max_cost_usd: Annotated[float, typer.Option("--max-cost-usd")] = 8.0,
    skip_existing: Annotated[bool, typer.Option("--skip-existing/--overwrite")] = True,
    limit: Annotated[int, typer.Option("--limit")] = 0,
) -> None:
    """Scrape LinkedIn employees for every FO that has a corporate_linkedin_url."""
    token = _resolve_token()
    if not token:
        raise typer.BadParameter(
            "No Apify token found in env (looked for APIFY_TOKEN, "
            "APIFY_TOKEN_1, APIFY_TOKEN_2, APIFY_TOKEN_3)."
        )
    if not _verify_token(token):
        raise typer.BadParameter("APIFY token failed authorization check.")

    if not dataset.exists():
        raise typer.BadParameter(f"dataset not found: {dataset}")
    df = pd.read_csv(dataset, dtype=str).fillna("")
    targets = df[df["corporate_linkedin_url"] != ""][
        ["record_id", "family_office_name", "corporate_linkedin_url"]
    ].to_dict(orient="records")
    if limit > 0:
        targets = targets[:limit]
    typer.echo(
        f"Targets: {len(targets)} FOs with LinkedIn URLs | "
        f"max_employees={max_employees} | budget=${max_cost_usd:.2f}"
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    spent_usd = 0.0
    scraped_rows = 0
    skipped_rows = 0
    error_rows = 0

    with httpx.Client() as client:
        for target in targets:
            record_id = target["record_id"]
            company_url = target["corporate_linkedin_url"]
            target_path = output_dir / f"{record_id}.json"
            if skip_existing and target_path.exists():
                skipped_rows += 1
                continue

            estimated_next = (max_employees + 1) * PRICE_PER_ITEM_USD
            if spent_usd + estimated_next > max_cost_usd:
                typer.echo(
                    f"  Budget reached (${spent_usd:.2f} of ${max_cost_usd:.2f}); "
                    f"stopping before {record_id}."
                )
                break

            typer.echo(f"  {record_id} | {target['family_office_name']!s}")
            items = _run_actor_for_company(client, token, company_url, max_employees)
            spent_usd += len(items) * PRICE_PER_ITEM_USD

            target_path.write_text(
                json.dumps(
                    {
                        "record_id": record_id,
                        "family_office_name": target["family_office_name"],
                        "company_url": company_url,
                        "scraped_at_utc": pd.Timestamp.utcnow().isoformat(),
                        "max_employees_requested": max_employees,
                        "actor_id": ACTOR_ID,
                        "items": items,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            errored = bool(items and items[0].get("_error"))
            if errored:
                error_rows += 1
            else:
                scraped_rows += 1
            time.sleep(0.5)  # tiny pause between runs

    typer.echo(
        f"Done: scraped={scraped_rows}, skipped={skipped_rows}, "
        f"errors={error_rows}. Estimated spend: ${spent_usd:.2f}."
    )


@app.command("summarize")
def summarize_results(
    output_dir: Annotated[Path, typer.Option("--output-dir")] = DEFAULT_OUTPUT_DIR,
) -> None:
    """Print coverage statistics across the scraped evidence files."""
    if not output_dir.exists():
        typer.echo(f"No directory: {output_dir}")
        return
    files = sorted(output_dir.glob("*.json"))
    total_items = 0
    empty_count = 0
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("items") or []
        if not items or (items and items[0].get("_error")):
            empty_count += 1
            continue
        plausible = [
            item for item in items
            if item.get("fullname") and item.get("profile_url")
        ]
        total_items += len(plausible)
        typer.echo(
            f"  {data['record_id']} | {data['family_office_name']:35s} "
            f"| employees={len(plausible)}"
        )
    typer.echo(
        f"\nTotal FOs scraped: {len(files)} | empty/error: {empty_count} | "
        f"total named employees: {total_items}"
    )


if __name__ == "__main__":
    app()
