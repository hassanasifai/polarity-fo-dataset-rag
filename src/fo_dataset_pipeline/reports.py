from __future__ import annotations

from pathlib import Path

from fo_dataset_pipeline.models import ValidatedFamilyOfficeRecord


def build_validation_report(records: list[ValidatedFamilyOfficeRecord]) -> str:
    accepted = [record for record in records if record.validation_status == "accepted"]
    needs_review = [record for record in records if record.validation_status != "accepted"]
    high = sum(1 for record in records if record.confidence == "high")
    medium = sum(1 for record in records if record.confidence == "medium")
    low = sum(1 for record in records if record.confidence == "low")

    lines = [
        "# Validation Report",
        "",
        "## Observed",
        f"- Input records processed: {len(records)}",
        f"- Accepted records: {len(accepted)}",
        f"- Needs review: {len(needs_review)}",
        f"- Confidence distribution: high={high}, medium={medium}, low={low}",
        "",
        "## Validation Rules",
        "- Required identity fields must parse through the Pydantic schema.",
        "- Accepted records require score >= 80, a reachable website, and at least two "
        "reachable source URLs.",
        "- SWFI-style discovery directory links are blocked from final acceptance.",
        "- Website and source URLs are checked with live HTTP requests.",
        "- Confidence is derived from source sufficiency, website reachability, "
        "evidence quality, and data completeness.",
        "",
        "## Records Needing Review",
    ]
    if needs_review:
        for record in needs_review:
            lines.append(
                f"- {record.family_office_name}: score={record.validation_score}, "
                f"confidence={record.confidence}, notes={record.validation_notes}"
            )
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def select_validation_chain_records(
    records: list[ValidatedFamilyOfficeRecord],
) -> list[ValidatedFamilyOfficeRecord]:
    selected: list[ValidatedFamilyOfficeRecord] = []
    preferred_types = [
        "single_family_office",
        "multi_family_office",
        "family_backed_investment_firm",
    ]
    for office_type in preferred_types:
        candidates = [
            record
            for record in records
            if record.family_office_type.value == office_type and record not in selected
        ]
        if candidates:
            selected.append(max(candidates, key=lambda item: item.validation_score))
    if len(selected) < 3:
        for record in sorted(records, key=lambda item: item.validation_score, reverse=True):
            if record not in selected:
                selected.append(record)
            if len(selected) == 3:
                break
    return selected[:3]


def build_validation_chains(records: list[ValidatedFamilyOfficeRecord], limit: int = 3) -> str:
    selected = select_validation_chain_records(records)[:limit]
    lines = ["# Three Full Validation Chains", ""]
    for record in selected:
        source_statuses = {
            check.url: (
                f"{check.status_code or 'ERR'} {check.final_url or check.error or ''}".strip()
            )
            for check in record.source_checks
        }
        lines.extend(
            [
                f"## {record.family_office_name}",
                "",
                f"- Record ID: {record.record_id}",
                f"- Office type: {record.family_office_type.value}",
                f"- Discovery source: {record.source_urls[0]}",
                f"- Extraction method: {record.extraction_method}",
                "- Extraction summary: fields were manually normalized from the listed public "
                "sources into entity identity, investment focus, location, principal or family "
                "context, and uncertainty notes.",
                "- Enrichment steps: official domain normalization, family-office type labeling, "
                "investment sector normalization, live website check, live source checks, "
                "sample-workbook overlap check, and confidence scoring.",
                "- Validation logic: required schema fields parsed; at least two source URLs were "
                "present; source URLs were checked with live HTTP requests; placeholder values "
                "and sample-workbook names were rejected before export.",
                f"- Confidence assessment: {record.confidence} ({record.validation_score}/100)",
                f"- Validation notes: {record.validation_notes}",
                "- Exact sources:",
            ]
        )
        for source_url in record.source_urls:
            source_status = source_statuses.get(str(source_url), "not checked")
            lines.append(f"  - {source_url} [{source_status}]")
        lines.extend(
            [
                f"- Website check: {record.website_check.status_code} "
                f"{record.website_check.final_url}",
                f"- Uncertainty notes: {record.uncertainty_notes or 'None recorded'}",
                "",
            ]
        )
    return "\n".join(lines)


def build_methodology_summary(records: list[ValidatedFamilyOfficeRecord]) -> str:
    accepted = [record for record in records if record.validation_status == "accepted"]
    high = sum(1 for record in records if record.confidence == "high")
    medium = sum(1 for record in records if record.confidence == "medium")
    low = sum(1 for record in records if record.confidence == "low")
    source_total = sum(record.source_count for record in records)
    lines = [
        "# Methodology Summary",
        "",
        "## How I Found Them",
        "",
        "- Started with broad public discovery, then replaced directory-dependent rows "
        "with candidates supported by official websites, official family-office service "
        "pages, SEC/IAPD-style disclosures, company registry pages, or official PDFs.",
        "- Excluded names copied from the provided sample workbook by comparing normalized "
        "entity names before export.",
        "- Mixed single-family offices, multi-family offices, family-backed investment "
        "firms, and family-originated foundations only when the row label makes that "
        "classification explicit.",
        "",
        "## How I Enriched Them",
        "",
        "- Normalized entity type, headquarters location, principal or family context, "
        "investment thesis, sector focus, AUM text when public, source notes, and "
        "uncertainty notes.",
        "- Left private contact fields blank unless the data was directly supportable from "
        "public business sources.",
        "- Preserved source URLs on every row and generated a separate source registry "
        "plus field-evidence table so the later RAG step can produce cited answers "
        "instead of unsourced summaries.",
        "",
        "## How I Validated Them",
        "",
        f"- Processed records: {len(records)}.",
        f"- Accepted records: {len(accepted)}.",
        f"- Total source links attached: {source_total}.",
        f"- Confidence distribution: high={high}, medium={medium}, low={low}.",
        "- Final source URLs no longer rely on SWFI-style discovery directories.",
        "- Pydantic validation rejects missing required fields, invalid URLs, weak "
        "single-source rows, placeholder values, and malformed emails.",
        "- Scoring rejects rows that lack a reachable official website or at least two "
        "reachable source URLs.",
        "- The CLI checks candidate names against the assessment sample workbook and "
        "fails if any normalized name overlaps.",
        "- The live validator requests the official website and every source URL and "
        "stores URL status metadata in the processed CSV, XLSX, and JSON outputs.",
        "- Final delivery gate used `--required-count 50`, so the run fails unless "
        "exactly 50 records are accepted.",
        "",
        "## What I Would Improve",
        "",
        "- Add claim-level evidence rows with exact snippets and source snapshots for each "
        "high-value field.",
        "- Add SEC ADV enrichment for registered advisers and store CRD or filing URLs.",
        "- Add archived copies or hashes of source artifacts so link rot does not weaken "
        "the audit trail.",
        "- Add a human review column for contradiction checks across official pages, "
        "regulatory filings, and third-party rankings.",
        "- Use the finalized dataset to build RAG chunks with record IDs, evidence IDs, "
        "source URLs, confidence scores, and validation status as metadata.",
    ]
    return "\n".join(lines) + "\n"


def write_reports(records: list[ValidatedFamilyOfficeRecord], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "validation_report.md").write_text(
        build_validation_report(records), encoding="utf-8"
    )
    (report_dir / "validation_chains.md").write_text(
        build_validation_chains(records), encoding="utf-8"
    )
    (report_dir / "methodology_summary.md").write_text(
        build_methodology_summary(records), encoding="utf-8"
    )
