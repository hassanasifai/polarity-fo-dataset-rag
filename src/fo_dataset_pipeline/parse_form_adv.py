"""Best-effort Form ADV PDF extraction for SEC-registered records.

This pass is intentionally conservative. It only promotes values that can be
found with deterministic patterns in the public SEC PDF text. When a pattern is
not reliable, the field stays blank and ``sec_form_adv_parse_status`` records
the outcome instead of guessing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated

import httpx
import pandas as pd
import typer
from pypdf import PdfReader

app = typer.Typer(no_args_is_help=True)

DEFAULT_DATASET = Path("data/processed/family_offices_validated.csv")
DEFAULT_JSON_OUTPUT = Path("data/processed/family_offices_validated.json")
DEFAULT_PDF_DIR = Path("data/evidence/form_adv_pdfs_2026_05_18")
DEFAULT_SEC_EVIDENCE_DIR = Path("data/evidence/sec_iapd_2026_05_17")

NEW_COLUMNS = (
    "sec_aum_usd",
    "sec_fee_structure",
    "sec_listed_officers",
    "sec_business_address",
    "sec_form_adv_parse_status",
    "sec_form_adv_evidence_path",
)

RAUM_RE = re.compile(
    r"Regulatory Assets Under Management.*?Total:\s*\(c\)\s*\$\s*([0-9,]+)",
    re.IGNORECASE | re.DOTALL,
)
FEE_PATTERNS = (
    ("asset_based_fees", re.compile(r"\basset[- ]based fees?\b", re.IGNORECASE)),
    ("fixed_fees", re.compile(r"\bfixed fees?\b", re.IGNORECASE)),
    ("hourly_fees", re.compile(r"\bhourly (fees?|charges?)\b", re.IGNORECASE)),
    ("performance_based_fees", re.compile(r"\bperformance[- ]based fees?\b", re.IGNORECASE)),
    ("other_advisory_fees", re.compile(r"\bother advisory fees?\b", re.IGNORECASE)),
)


def _download_pdf(url: str, output_path: Path) -> bool:
    if output_path.exists() and output_path.stat().st_size > 0:
        return True
    response = httpx.get(url, timeout=45.0, follow_redirects=True)
    if response.status_code >= 400 or not response.content:
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)
    return True


def _extract_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_aum_usd(text: str) -> str:
    match = RAUM_RE.search(text)
    if not match:
        return ""
    return match.group(1).replace(",", "")


def _extract_fee_structure(text: str) -> str:
    labels = [label for label, pattern in FEE_PATTERNS if pattern.search(text)]
    return "; ".join(labels)


def _business_address(record: dict[str, str], sec_evidence_dir: Path) -> str:
    evidence_path = sec_evidence_dir / f"{record['record_id']}.json"
    if not evidence_path.exists():
        return ""
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    address = payload.get("sec_address") or {}
    parts = [
        address.get("street1"),
        address.get("street2"),
        address.get("city"),
        address.get("state"),
        address.get("postal_code"),
        address.get("country"),
    ]
    return ", ".join(str(part).strip() for part in parts if str(part or "").strip())


def enrich_form_adv_fields(
    df: pd.DataFrame,
    pdf_dir: Path = DEFAULT_PDF_DIR,
    sec_evidence_dir: Path = DEFAULT_SEC_EVIDENCE_DIR,
) -> pd.DataFrame:
    output = df.copy()
    for column in NEW_COLUMNS:
        if column not in output.columns:
            output[column] = ""

    for index, row in output.iterrows():
        url = str(row.get("form_adv_brochure_url") or "").strip()
        record_id = str(row.get("record_id") or "").strip()
        if not url or not record_id:
            output.at[index, "sec_form_adv_parse_status"] = "no_form_adv_url"
            continue

        pdf_path = pdf_dir / f"{record_id}.pdf"
        if not _download_pdf(url, pdf_path):
            output.at[index, "sec_form_adv_parse_status"] = "download_failed"
            continue

        output.at[index, "sec_form_adv_evidence_path"] = url
        output.at[index, "sec_business_address"] = _business_address(
            row.to_dict(), sec_evidence_dir
        )
        try:
            text = _extract_text(pdf_path)
        except Exception as exc:  # pragma: no cover - defensive for malformed PDFs
            output.at[index, "sec_form_adv_parse_status"] = (
                f"text_extract_failed:{type(exc).__name__}"
            )
            continue

        output.at[index, "sec_aum_usd"] = _extract_aum_usd(text)
        output.at[index, "sec_fee_structure"] = _extract_fee_structure(text)
        output.at[index, "sec_form_adv_parse_status"] = (
            "parsed_with_aum"
            if output.at[index, "sec_aum_usd"]
            else "parsed_no_reliable_aum_pattern"
        )

    return output


@app.command("run")
def run_parse(
    dataset: Annotated[Path, typer.Option("--dataset")] = DEFAULT_DATASET,
    json_output: Annotated[Path, typer.Option("--json-output")] = DEFAULT_JSON_OUTPUT,
    pdf_dir: Annotated[Path, typer.Option("--pdf-dir")] = DEFAULT_PDF_DIR,
    sec_evidence_dir: Annotated[
        Path, typer.Option("--sec-evidence-dir")
    ] = DEFAULT_SEC_EVIDENCE_DIR,
) -> None:
    """Download SEC PDFs and promote conservative Form ADV fields."""
    if not dataset.exists():
        raise typer.BadParameter(f"dataset not found: {dataset}")

    df = pd.read_csv(dataset, dtype=str).fillna("")
    output = enrich_form_adv_fields(df, pdf_dir=pdf_dir, sec_evidence_dir=sec_evidence_dir)
    output.to_csv(dataset, index=False)
    json_output.write_text(
        json.dumps(output.fillna("").to_dict(orient="records"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    status_counts = output["sec_form_adv_parse_status"].value_counts().to_dict()
    typer.echo(f"Form ADV parse complete for {len(output)} rows: {status_counts}")


if __name__ == "__main__":
    app()
