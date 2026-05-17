from __future__ import annotations

import asyncio
import csv
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

import httpx
import pandas as pd
import typer

app = typer.Typer(no_args_is_help=True)

APIFY_BASE_URL = "https://api.apify.com/v2"
GOOGLE_ACTOR_ID = "apify/google-search-scraper"
CRAWLER_ACTOR_ID = "apify/website-content-crawler"
RUN_LOG_HEADER = [
    "run_label",
    "actor_id",
    "run_purpose",
    "region_batch",
    "started_at_utc",
    "finished_at_utc",
    "run_id",
    "status",
    "item_count",
    "credits_used_usd",
    "export_json_path",
    "export_csv_path",
    "candidate_count_added",
    "limitations",
]

US_DISCOVERY_QUERIES = [
    '"single family office" "investments" "official"',
    '"multi-family office" "Form ADV" "family office services"',
    '"family office services" "Form ADV Part 2A"',
    '"family investment office" "portfolio"',
    '"single-family office" "portfolio"',
    '"family office" "direct investments" "team"',
]

GLOBAL_DISCOVERY_QUERIES = [
    '"single family office" "official website" "investment office"',
    '"multi-family office" "official website" "family office services"',
    '"family office" "Companies House"',
    '"family office" "Singapore" "investment office"',
    '"family office" "Hong Kong" "multi-family office"',
    '"family office" "Switzerland" "investment office"',
]
REJECT_DISCOVERY_DOMAINS = {
    "adviserinfo.sec.gov",
    "crunchbase.com",
    "familyoffices.com",
    "linkedin.com",
    "pitchbook.com",
    "simplefamilyoffice.com",
    "swfinstitute.org",
    "wikipedia.org",
    "youtube.com",
    "zoominfo.com",
}
NON_ENTITY_TERMS = {
    "article",
    "conference",
    "considerations",
    "compliance",
    "fund manager",
    "guide",
    "insight",
    "largest",
    "list of",
    "market research",
    "monthly theme",
    "news",
    "operational playbook",
    "overview",
    "podcast",
    "regulations",
    "similar companies",
    "summit",
    "top family offices",
    "what i learned",
}


def actor_path(actor_id: str) -> str:
    return actor_id.replace("/", "~")


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def token_from_env() -> str:
    token = os.getenv("APIFY_TOKEN")
    if not token:
        raise typer.BadParameter("APIFY_TOKEN is required in the process environment")
    return token


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def evidence_export_dir(root: Path | None = None) -> Path:
    base = root or project_root()
    path = base / "data" / "evidence" / "raw_apify_exports" / datetime.now(UTC).date().isoformat()
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_run_log_path(root: Path | None = None) -> Path:
    base = root or project_root()
    return base / "docs" / "apify_run_log.csv"


def ensure_run_log(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerow(RUN_LOG_HEADER)


def append_run_log(path: Path, row: dict[str, Any]) -> None:
    ensure_run_log(path)
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RUN_LOG_HEADER)
        writer.writerow({key: row.get(key, "") for key in RUN_LOG_HEADER})


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


async def run_actor_and_get_items(
    actor_id: str,
    actor_input: dict[str, Any],
    token: str,
    wait_for_finish: int = 300,
    timeout_seconds: int = 600,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    run_url = f"{APIFY_BASE_URL}/acts/{actor_path(actor_id)}/runs"
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        run_response = await client.post(
            run_url,
            params={"token": token, "waitForFinish": wait_for_finish},
            json=actor_input,
        )
        run_response.raise_for_status()
        run_data = run_response.json()["data"]
        run_id = run_data["id"]
        while run_data["status"] not in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
            await asyncio.sleep(10)
            poll_response = await client.get(
                f"{APIFY_BASE_URL}/actor-runs/{run_id}",
                params={"token": token},
            )
            poll_response.raise_for_status()
            run_data = poll_response.json()["data"]

        dataset_id = run_data.get("defaultDatasetId")
        if not dataset_id:
            return run_data, []
        dataset_response = await client.get(
            f"{APIFY_BASE_URL}/datasets/{dataset_id}/items",
            params={"token": token, "format": "json", "clean": "true", "limit": 250000},
        )
        dataset_response.raise_for_status()
        return run_data, dataset_response.json()


def google_search_input(queries: list[str], country_code: str) -> dict[str, Any]:
    return {
        "queries": "\n".join(queries),
        "countryCode": country_code,
        "languageCode": "en",
        "searchLanguage": "en",
        "resultsPerPage": 20,
        "maxPagesPerQuery": 1,
        "mobileResults": False,
        "includeUnfilteredResults": False,
        "saveHtml": False,
        "saveHtmlToKeyValueStore": False,
        "maximumLeadsEnrichmentRecords": 0,
        "focusOnPaidAds": False,
    }


def website_crawler_input(source_urls: list[str]) -> dict[str, Any]:
    return {
        "startUrls": [{"url": url} for url in source_urls],
        "crawlerType": "playwright:adaptive",
        "maxCrawlDepth": 0,
        "maxCrawlPages": len(source_urls),
        "maxResults": len(source_urls),
        "includeUrlGlobs": [],
        "excludeUrlGlobs": [
            "**/privacy**",
            "**/terms**",
            "**/cookie**",
            "**/cookies**",
            "**/login**",
            "**/signin**",
            "**/wp-admin**",
            "**/careers**",
            "**/jobs**",
            "**/events**",
            "**/podcast**",
            "**/video**",
        ],
        "useSitemaps": False,
        "useLlmsTxt": False,
        "respectRobotsTxtFile": True,
        "proxyConfiguration": {"useApifyProxy": True},
        "blockMedia": True,
        "removeCookieWarnings": True,
        "htmlTransformer": "readableText",
        "saveMarkdown": True,
        "saveHtmlAsFile": False,
        "storeSkippedUrls": True,
        "dynamicContentWaitSecs": 8,
        "maxConcurrency": 5,
        "maxRequestRetries": 2,
    }


def source_urls_from_dataset(path: Path, limit: int | None = None) -> list[str]:
    df = pd.read_csv(path)
    urls: list[str] = []
    for value in df["source_urls"].dropna():
        raw = str(value).strip()
        if raw.startswith("["):
            for item in json.loads(raw.replace("'", '"')):
                if item not in urls:
                    urls.append(item)
        else:
            for item in raw.replace("\n", ";").split(";"):
                url = item.strip()
                if url and url not in urls:
                    urls.append(url)
    non_pdf_urls = [url for url in urls if not url.lower().endswith(".pdf")]
    return non_pdf_urls[:limit] if limit is not None else non_pdf_urls


def canonical_url(url: str) -> str:
    return url.split("#", 1)[0].rstrip("/")


def domain_from_url(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def evidence_snippet(markdown: str, max_chars: int = 600) -> str:
    cleaned = re.sub(r"\s+", " ", markdown).strip()
    if not cleaned:
        return ""
    keyword_pattern = re.compile(
        r"(single[- ]family office|multi[- ]family office|family office|investment|"
        r"Form ADV|portfolio|wealth)",
        re.IGNORECASE,
    )
    for sentence in re.split(r"(?<=[.!?])\s+", cleaned):
        if keyword_pattern.search(sentence):
            return sentence[:max_chars]
    return cleaned[:max_chars]


def triage_serp_result(title: str, description: str, url: str) -> tuple[str, str]:
    domain = domain_from_url(url)
    text = f"{title} {description}".lower()
    blocked_domain = any(
        domain == blocked or domain.endswith(f".{blocked}")
        for blocked in REJECT_DISCOVERY_DOMAINS
    )
    if blocked_domain:
        return "reject", "directory/social/regulator result; use only as corroboration or lookup"
    if any(term in text for term in NON_ENTITY_TERMS):
        return "reject", "non-entity result"
    if "family office" not in text and "family-office" not in text:
        return "reject", "snippet/title lacks direct family-office language"
    return "candidate_raw", "own-domain result with direct family-office language"


def flatten_serp_items(serp_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in serp_items:
        query = item.get("searchQuery", {}).get("term", "")
        for result in item.get("organicResults", []):
            title = result.get("title", "")
            description = result.get("description", "")
            url = result.get("url", "")
            status, reason = triage_serp_result(title, description, url)
            rows.append(
                {
                    "query": query,
                    "position": result.get("position", ""),
                    "title": title,
                    "url": url,
                    "domain": domain_from_url(url),
                    "description": description,
                    "triage_status": status,
                    "triage_reason": reason,
                }
            )
    return rows


def build_apify_evidence_rows(
    source_registry_path: Path,
    crawler_json_path: Path,
) -> list[dict[str, Any]]:
    source_df = pd.read_csv(source_registry_path)
    crawler_items = json.loads(crawler_json_path.read_text(encoding="utf-8"))
    crawl_by_url = {
        canonical_url(str(item.get("url", ""))): item
        for item in crawler_items
        if item.get("url")
    }
    rows: list[dict[str, Any]] = []
    for source in source_df.to_dict(orient="records"):
        source_url = str(source["source_url"])
        is_pdf = source_url.lower().endswith(".pdf")
        item = crawl_by_url.get(canonical_url(source_url))
        markdown = item.get("markdown") or item.get("text") or "" if item else ""
        rows.append(
            {
                "source_id": source["source_id"],
                "record_id": source["record_id"],
                "family_office_name": source["family_office_name"],
                "source_url": source_url,
                "source_type": source["source_type"],
                "apify_matched": bool(item),
                "apify_crawled_url": item.get("url", "") if item else "",
                "is_pdf": is_pdf,
                "markdown_chars": len(markdown),
                "evidence_snippet": evidence_snippet(markdown),
                "html_url": item.get("htmlUrl", "") if item else "",
                "screenshot_url": item.get("screenshotUrl", "") if item else "",
                "notes": "PDF excluded from website-content-crawler"
                if is_pdf
                else "Matched by canonical URL without fragment"
                if item and canonical_url(source_url) != source_url.rstrip("/")
                else "No Apify crawl item returned"
                if not item
                else "Matched",
            }
        )
    return rows


@app.command("write-inputs")
def write_inputs(
    output_dir: Annotated[Path, typer.Option("--output-dir")] = Path(
        "data/evidence/apify_inputs"
    ),
    dataset: Annotated[Path, typer.Option("--dataset")] = Path(
        "data/raw/family_offices_seed.csv"
    ),
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        output_dir / "google_search_us.json",
        google_search_input(US_DISCOVERY_QUERIES, "us"),
    )
    write_json(
        output_dir / "google_search_global.json",
        google_search_input(GLOBAL_DISCOVERY_QUERIES, "gb"),
    )
    source_urls = source_urls_from_dataset(dataset)
    write_json(output_dir / "website_exact_evidence_urls.json", website_crawler_input(source_urls))
    typer.echo(f"Wrote Apify input configs to {output_dir}")


@app.command("run-search")
def run_search(
    run_label: Annotated[str, typer.Option("--run-label")],
    country_code: Annotated[str, typer.Option("--country-code")] = "us",
    query_set: Annotated[str, typer.Option("--query-set")] = "us",
    wait_for_finish: Annotated[int, typer.Option("--wait-for-finish")] = 300,
) -> None:
    queries = US_DISCOVERY_QUERIES if query_set == "us" else GLOBAL_DISCOVERY_QUERIES
    actor_input = google_search_input(queries, country_code)
    started_at = utc_now()
    run_data, items = asyncio.run(
        run_actor_and_get_items(
            GOOGLE_ACTOR_ID,
            actor_input,
            token_from_env(),
            wait_for_finish=wait_for_finish,
        )
    )
    export_dir = evidence_export_dir()
    json_path = export_dir / f"{run_label}.json"
    csv_path = export_dir / f"{run_label}.csv"
    write_json(json_path, items)
    write_csv(csv_path, items)
    append_run_log(
        default_run_log_path(),
        {
            "run_label": run_label,
            "actor_id": GOOGLE_ACTOR_ID,
            "run_purpose": "Discovery",
            "region_batch": country_code,
            "started_at_utc": started_at,
            "finished_at_utc": utc_now(),
            "run_id": run_data.get("id"),
            "status": run_data.get("status"),
            "item_count": len(items),
            "credits_used_usd": run_data.get("usageTotalUsd", ""),
            "export_json_path": json_path,
            "export_csv_path": csv_path,
            "candidate_count_added": "",
            "limitations": "SERP output is discovery only; rows require manual validation.",
        },
    )
    typer.echo(f"Exported {len(items)} SERP items to {json_path}")


@app.command("run-evidence-crawl")
def run_evidence_crawl(
    run_label: Annotated[str, typer.Option("--run-label")],
    dataset: Annotated[Path, typer.Option("--dataset")] = Path(
        "data/raw/family_offices_seed.csv"
    ),
    limit: Annotated[int | None, typer.Option("--limit")] = None,
    wait_for_finish: Annotated[int, typer.Option("--wait-for-finish")] = 300,
) -> None:
    source_urls = source_urls_from_dataset(dataset, limit=limit)
    actor_input = website_crawler_input(source_urls)
    started_at = utc_now()
    run_data, items = asyncio.run(
        run_actor_and_get_items(
            CRAWLER_ACTOR_ID,
            actor_input,
            token_from_env(),
            wait_for_finish=wait_for_finish,
        )
    )
    export_dir = evidence_export_dir()
    json_path = export_dir / f"{run_label}.json"
    csv_path = export_dir / f"{run_label}.csv"
    write_json(json_path, items)
    write_csv(csv_path, items)
    append_run_log(
        default_run_log_path(),
        {
            "run_label": run_label,
            "actor_id": CRAWLER_ACTOR_ID,
            "run_purpose": "Evidence capture",
            "region_batch": "exact_source_urls",
            "started_at_utc": started_at,
            "finished_at_utc": utc_now(),
            "run_id": run_data.get("id"),
            "status": run_data.get("status"),
            "item_count": len(items),
            "credits_used_usd": run_data.get("usageTotalUsd", ""),
            "export_json_path": json_path,
            "export_csv_path": csv_path,
            "candidate_count_added": "",
            "limitations": "Depth-0 crawl of exact evidence URLs; PDFs excluded.",
        },
    )
    typer.echo(f"Exported {len(items)} crawled evidence items to {json_path}")


@app.command("build-evidence-summary")
def build_evidence_summary(
    crawler_json: Annotated[Path, typer.Option("--crawler-json")],
    source_registry: Annotated[Path, typer.Option("--source-registry")] = Path(
        "data/processed/source_registry.csv"
    ),
    output: Annotated[Path, typer.Option("--output")] = Path(
        "data/processed/apify_crawl_evidence.csv"
    ),
    workbook: Annotated[Path | None, typer.Option("--workbook")] = Path(
        "data/processed/family_offices_validated.xlsx"
    ),
) -> None:
    rows = build_apify_evidence_rows(source_registry, crawler_json)
    write_csv(output, rows)
    if workbook is not None and workbook.exists():
        with pd.ExcelWriter(
            workbook,
            engine="openpyxl",
            mode="a",
            if_sheet_exists="replace",
        ) as writer:
            pd.DataFrame(rows).to_excel(writer, sheet_name="apify_evidence", index=False)
    matched = sum(1 for row in rows if row["apify_matched"])
    typer.echo(f"Wrote {len(rows)} Apify evidence rows; matched {matched}")


@app.command("flatten-serp")
def flatten_serp(
    serp_json: Annotated[Path, typer.Option("--serp-json")],
    output: Annotated[Path, typer.Option("--output")] = Path(
        "data/evidence/candidates_raw_from_apify.csv"
    ),
) -> None:
    serp_items = json.loads(serp_json.read_text(encoding="utf-8"))
    rows = flatten_serp_items(serp_items)
    write_csv(output, rows)
    kept = sum(1 for row in rows if row["triage_status"] == "candidate_raw")
    typer.echo(f"Wrote {len(rows)} SERP result rows; candidate_raw={kept}")


if __name__ == "__main__":
    app()
