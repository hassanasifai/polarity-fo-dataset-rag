"""Query the SEC IAPD public API for each FO's regulatory record.

Uses the FREE, AUTHORITATIVE endpoint
``https://api.adviserinfo.sec.gov/search/firm?query=...`` to look up each
family-office firm. Stores per-FO evidence JSON under
``data/evidence/sec_iapd_2026_05_17/`` for the downstream promoter.

The search API returns:
- ``firm_source_id`` (the CRD number)
- ``firm_ia_full_sec_number`` (e.g. "801-70776")
- ``firm_name`` + ``firm_other_names`` (aliases / DBAs)
- ``firm_ia_scope`` ("ACTIVE" / "INACTIVE")
- ``firm_branches_count``
- ``firm_ia_address_details`` (street/city/state/country/postalCode)

Matching strategy (conservative, high precision):
1. Try the FO's full registered name first.
2. Try a simplified variant (drop "Family Office", "Capital", "LLC", etc.).
3. Accept a hit only when the normalized firm name (or any alias) matches the
   FO name to within a tight Jaccard threshold, OR the city + state from
   ``firm_ia_address_details`` matches the FO's HQ city + state.

For every FO we write an evidence file — even when there is no match — so the
promoter can write an explicit ``sec_registered = false`` row with a sourced
explanation rather than silently skipping.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Annotated

import httpx
import pandas as pd
import typer

app = typer.Typer(no_args_is_help=True)

IAPD_SEARCH_URL = "https://api.adviserinfo.sec.gov/search/firm"
DEFAULT_USER_AGENT = "PolarityIQ FO Dataset Research polarityiq.research@example.com"
DEFAULT_OUTPUT_DIR = Path("data/evidence/sec_iapd_2026_05_17")
DEFAULT_DATASET_PATH = Path("data/processed/family_offices_validated.csv")

DROP_TOKENS = {
    "family", "office", "offices", "capital", "wealth", "management",
    "advisors", "advisor", "advisory", "partners", "group", "llc", "inc",
    "llp", "ltd", "co", "corp", "company", "holdings", "limited", "the",
    "&", "and",
}


def _normalize_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9 ]", " ", name).lower()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _simplify_name(name: str) -> str:
    tokens = [
        token
        for token in _normalize_name(name).split()
        if token not in DROP_TOKENS
    ]
    return " ".join(tokens)


def _name_jaccard(left: str, right: str) -> float:
    a = set(_normalize_name(left).split())
    b = set(_normalize_name(right).split())
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _simplified_name_match(left: str, right: str) -> bool:
    left_simple = _simplify_name(left)
    right_simple = _simplify_name(right)
    return bool(left_simple and right_simple and left_simple == right_simple)


def _candidate_queries(record: dict) -> list[str]:
    name = str(record.get("family_office_name") or "").strip()
    if not name:
        return []
    queries = [name]
    simplified = _simplify_name(name)
    if simplified and simplified != _normalize_name(name):
        queries.append(simplified)
    # Also try the first 2 distinctive tokens (drops generic suffixes).
    first_tokens = simplified.split()
    if first_tokens:
        queries.append(" ".join(first_tokens[:2]))
    # De-dupe while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for query in queries:
        key = query.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(query)
    return out


def _query_iapd(
    client: httpx.Client, query: str, page_size: int = 10
) -> list[dict]:
    response = client.get(
        IAPD_SEARCH_URL,
        params={
            "query": query,
            "hl": "true",
            "nrows": page_size,
            "start": 0,
        },
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json",
        },
        timeout=15.0,
    )
    response.raise_for_status()
    body = response.json() or {}
    hits = (body.get("hits") or {}).get("hits") or []
    return [hit.get("_source") or {} for hit in hits if hit.get("_source")]


def _score_hit(hit: dict, record: dict) -> tuple[float, str]:
    """Return (score, reason). Higher score = better match. Threshold = 0.6."""
    fo_name = record.get("family_office_name") or ""
    fo_city = (record.get("city") or "").strip().lower()
    fo_state = (record.get("state_region") or "").strip().lower()

    names: list[str] = [hit.get("firm_name") or ""]
    others = hit.get("firm_other_names") or []
    if isinstance(others, list):
        names.extend(str(item) for item in others if item)
    elif isinstance(others, str):
        names.append(others)

    best_jaccard = 0.0
    best_match_name = ""
    simplified_exact = False
    for candidate in names:
        score = _name_jaccard(fo_name, candidate)
        if score > best_jaccard:
            best_jaccard = score
            best_match_name = candidate
        if _simplified_name_match(fo_name, candidate):
            simplified_exact = True
            best_match_name = candidate

    # Address corroboration adds confidence.
    address_match = False
    raw_address = hit.get("firm_ia_address_details") or ""
    if isinstance(raw_address, str) and raw_address.startswith("{"):
        try:
            addr = json.loads(raw_address).get("officeAddress") or {}
        except json.JSONDecodeError:
            addr = {}
    elif isinstance(raw_address, dict):
        addr = raw_address.get("officeAddress") or raw_address
    else:
        addr = {}

    hit_city = str(addr.get("city") or "").strip().lower()
    hit_state = str(addr.get("state") or "").strip().lower()
    if fo_city and hit_city and fo_city == hit_city:
        if fo_state and hit_state and fo_state in {hit_state, hit_state[:2]}:
            address_match = True

    score = 0.75 if simplified_exact else best_jaccard
    if address_match:
        score += 0.25

    reasons: list[str] = []
    reasons.append(f"name_jaccard={best_jaccard:.2f} (vs '{best_match_name}')")
    if simplified_exact:
        reasons.append("simplified_name_exact_match")
    if address_match:
        reasons.append("address_match=city+state")
    return score, "; ".join(reasons)


def _build_brochure_url(crd: str) -> str:
    return f"https://reports.adviserinfo.sec.gov/reports/ADV/{crd}/PDF/{crd}.pdf"


def _build_summary_url(crd: str) -> str:
    return f"https://adviserinfo.sec.gov/firm/summary/{crd}"


def _match_record(
    client: httpx.Client, record: dict, threshold: float = 0.6
) -> dict:
    """Return evidence dict for one FO record."""
    queries_tried: list[dict] = []
    best_hit: dict | None = None
    best_score: float = 0.0
    best_reason: str = ""

    for query in _candidate_queries(record):
        try:
            hits = _query_iapd(client, query)
        except httpx.HTTPError as exc:
            queries_tried.append({"query": query, "error": str(exc)})
            continue
        queries_tried.append({"query": query, "hit_count": len(hits)})
        for hit in hits:
            score, reason = _score_hit(hit, record)
            if score > best_score:
                best_score = score
                best_hit = hit
                best_reason = reason
        if best_score >= threshold and best_hit is not None:
            break  # good match — stop trying more queries
        time.sleep(0.3)  # be polite to the SEC API

    evidence: dict = {
        "record_id": record.get("record_id"),
        "family_office_name": record.get("family_office_name"),
        "queried_at_utc": pd.Timestamp.utcnow().isoformat(),
        "queries_tried": queries_tried,
        "match_threshold": threshold,
        "match_score": round(best_score, 3),
        "match_reason": best_reason,
    }

    if best_hit is None or best_score < threshold:
        evidence["sec_registered"] = False
        if best_hit is not None and best_score >= 0.45:
            evidence["manual_review_status"] = "needs_review"
            evidence["manual_review_reason"] = (
                "IAPD returned a threshold-edge firm match; do not treat as a legal "
                "non-registration claim until a human reviews the CRD and aliases."
            )
        evidence["notes"] = (
            "No IAPD match above threshold in the automated pass. This is a "
            "dataset-snapshot finding, not a legal conclusion."
        )
        return evidence

    raw_address = best_hit.get("firm_ia_address_details") or ""
    if isinstance(raw_address, str) and raw_address.startswith("{"):
        try:
            addr = json.loads(raw_address).get("officeAddress") or {}
        except json.JSONDecodeError:
            addr = {}
    elif isinstance(raw_address, dict):
        addr = raw_address.get("officeAddress") or raw_address
    else:
        addr = {}

    crd = str(best_hit.get("firm_source_id") or "")
    sec_full = str(best_hit.get("firm_ia_full_sec_number") or "")
    sec_short = str(best_hit.get("firm_ia_sec_number") or "")
    scope = str(best_hit.get("firm_ia_scope") or "").upper()

    evidence["sec_registered"] = True
    evidence["sec_crd_number"] = crd
    evidence["sec_file_number"] = sec_full or sec_short
    evidence["sec_registration_status"] = scope or "UNKNOWN"
    evidence["firm_name_iapd"] = best_hit.get("firm_name") or ""
    evidence["firm_other_names"] = best_hit.get("firm_other_names") or []
    evidence["firm_branches_count"] = best_hit.get("firm_branches_count")
    evidence["sec_address"] = {
        "street1": addr.get("street1"),
        "street2": addr.get("street2"),
        "city": addr.get("city"),
        "state": addr.get("state"),
        "country": addr.get("country"),
        "postal_code": addr.get("postalCode"),
    }
    evidence["form_adv_brochure_url"] = _build_brochure_url(crd)
    evidence["sec_summary_url"] = _build_summary_url(crd)
    return evidence


@app.command("run")
def run_research(
    dataset: Annotated[Path, typer.Option("--dataset")] = DEFAULT_DATASET_PATH,
    output_dir: Annotated[Path, typer.Option("--output-dir")] = DEFAULT_OUTPUT_DIR,
    threshold: Annotated[float, typer.Option("--threshold")] = 0.6,
    skip_existing: Annotated[bool, typer.Option("--skip-existing/--overwrite")] = True,
) -> None:
    """Query SEC IAPD for each FO and persist per-record evidence JSON."""
    if not dataset.exists():
        raise typer.BadParameter(f"dataset not found: {dataset}")
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(dataset).fillna("")
    matched = 0
    unmatched = 0
    skipped = 0

    with httpx.Client() as client:
        for record in df.to_dict(orient="records"):
            record_id = str(record.get("record_id") or "").strip()
            if not record_id:
                continue
            target = output_dir / f"{record_id}.json"
            if skip_existing and target.exists():
                skipped += 1
                continue
            evidence = _match_record(client, record, threshold=threshold)
            target.write_text(
                json.dumps(evidence, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            if evidence.get("sec_registered"):
                matched += 1
            else:
                unmatched += 1
            time.sleep(0.2)

    typer.echo(
        f"IAPD research complete: matched={matched}, unmatched={unmatched}, "
        f"skipped={skipped}. Evidence in {output_dir}."
    )


@app.command("summarize")
def summarize_results(
    output_dir: Annotated[Path, typer.Option("--output-dir")] = DEFAULT_OUTPUT_DIR,
) -> None:
    """Print a coverage summary across all evidence files."""
    if not output_dir.exists():
        typer.echo(f"No evidence directory at {output_dir}.")
        return
    matched: list[dict] = []
    unmatched: list[dict] = []
    for path in sorted(output_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("sec_registered"):
            matched.append(data)
        else:
            unmatched.append(data)
    typer.echo(f"Total: {len(matched) + len(unmatched)}")
    typer.echo(f"  SEC-registered (matched): {len(matched)}")
    typer.echo(f"  Not registered: {len(unmatched)}")
    if matched:
        typer.echo("\nMatched firms:")
        for data in matched[:20]:
            typer.echo(
                f"  {data['record_id']} | {data['family_office_name']} | "
                f"CRD={data['sec_crd_number']} | {data['firm_name_iapd']} | "
                f"score={data['match_score']}"
            )


if __name__ == "__main__":
    app()
