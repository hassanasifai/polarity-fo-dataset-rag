"""Append claim-level evidence rows for post-validation promoted fields.

The original validator builds field evidence only for seed/schema fields. Later
promoters add high-value columns (SEC identifiers, LinkedIn company data,
social handles, Google Places corroboration, street address, principal slots,
sample-parity fields). This module makes those promotions auditable by adding a
stable ``*_augmented_*`` claim row for every non-empty promoted value.
"""
from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import pandas as pd
import typer

app = typer.Typer(no_args_is_help=True)

DEFAULT_DATASET = Path("data/processed/family_offices_validated.csv")
DEFAULT_FIELD_EVIDENCE = Path("data/processed/field_evidence.csv")
DEFAULT_SEC_EVIDENCE_DIR = Path("data/evidence/sec_iapd_2026_05_17")
METHODOLOGY_SOURCE = "reports/methodology_summary.md"
AUGMENTED_MARKER = "_augmented_"

GROUPS: tuple[dict, ...] = (
    {
        "fields": ("primary_email",),
        "evidence": "primary_email_evidence_url",
        "confidence": "primary_email_confidence",
        "claim_type": "promoted_contact",
        "logic": "Promoted only when public contact evidence and confidence label were present.",
    },
    {
        "fields": ("primary_phone",),
        "evidence": "primary_phone_evidence_url",
        "confidence": "primary_phone_confidence",
        "claim_type": "promoted_contact",
        "logic": "Promoted only when public phone evidence and confidence label were present.",
    },
    {
        "fields": ("corporate_linkedin_url",),
        "evidence": "corporate_linkedin_evidence_url",
        "confidence": "corporate_linkedin_confidence",
        "claim_type": "promoted_linkedin_company",
        "logic": (
            "Corporate LinkedIn URL retained only from LinkedIn/company evidence "
            "or official-site link."
        ),
    },
    {
        "fields": (
            "linkedin_employee_count",
            "linkedin_follower_count",
            "linkedin_specialties",
            "linkedin_company_size_band",
            "linkedin_industry",
            "linkedin_founded_year",
            "linkedin_headquarters_full",
        ),
        "evidence": "linkedin_company_evidence_url",
        "confidence": "linkedin_company_confidence",
        "claim_type": "linkedin_company_enrichment",
        "logic": (
            "LinkedIn company row joined only when LinkedIn website domain matched "
            "FO website domain."
        ),
    },
    {
        "fields": ("twitter_url", "instagram_url", "facebook_url", "youtube_url", "tiktok_url"),
        "evidence": "social_media_evidence_url",
        "confidence": "social_media_confidence",
        "claim_type": "official_site_social_link",
        "logic": "Social handle retained only when discovered from the FO official-site crawl.",
    },
    {
        "fields": (
            "google_places_phone",
            "google_places_reviews_count",
            "google_places_rating",
            "google_places_category",
            "google_maps_url",
            "primary_phone_corroborated_by_places",
        ),
        "evidence": "google_places_evidence_url",
        "confidence": "google_places_confidence",
        "claim_type": "google_places_corroboration",
        "logic": (
            "Google Places row retained only when returned website domain matched "
            "FO website domain."
        ),
    },
    {
        "fields": ("street_address",),
        "evidence": "street_address_evidence_url",
        "confidence": "street_address_confidence",
        "claim_type": "address_corroboration",
        "logic": "Street address promoted from domain-matched Places or LinkedIn company evidence.",
    },
    {
        "fields": (
            "sec_crd_number",
            "sec_file_number",
            "sec_registration_status",
            "sec_firm_name_iapd",
            "sec_firm_other_names",
            "sec_branches_count",
            "form_adv_brochure_url",
            "sec_summary_url",
            "sec_address_city",
            "sec_address_state",
            "sec_address_country",
        ),
        "evidence": "sec_evidence_url",
        "confidence": "sec_confidence",
        "claim_type": "regulatory_identifier",
        "logic": (
            "SEC IAPD match accepted only above threshold with CRD-backed adviser "
            "summary URL."
        ),
    },
)

DERIVED_FIELDS = {
    "contact_first_name": "Derived from validated principal/contact full name.",
    "contact_last_name": "Derived from validated principal/contact full name.",
    "contact_full_name": "Copied from validated principal/contact full name.",
    "contact_location": "Derived from validated city, state/region, and country.",
    "data_completion_score_text": "Computed against the sample-workbook denominator.",
    "data_completion_score_visual": "Rendered from data_completion_score_text.",
    "secondary_email_validation_code": "Explicit no-secondary-evidence marker.",
    "email_code_explanation_secondary": "Human-readable explanation for absent secondary email.",
    "email_quality_assessment_secondary": "Explicit no-secondary-evidence marker.",
}


def _nonempty(value: object) -> bool:
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    return bool(str(value).strip())


def _domain(url: str) -> str:
    text = str(url or "").strip()
    if not text or text.startswith("reports/") or text.startswith("data/"):
        return ""
    if "://" not in text:
        text = "https://" + text
    return urlparse(text).netloc.lower().removeprefix("www.")


def _source_type(source_url: str, website_url: str) -> str:
    source_domain = _domain(source_url)
    website_domain = _domain(website_url)
    if not source_url:
        return "unknown"
    if source_url.startswith("reports/"):
        return "methodology"
    if source_url.startswith("data/"):
        return "local_evidence_artifact"
    if source_domain == website_domain:
        return "official_site"
    if "linkedin.com" in source_domain:
        return "linkedin"
    if "adviserinfo.sec.gov" in source_domain or "reports.adviserinfo.sec.gov" in source_domain:
        return "regulator"
    if "google.com" in source_domain:
        return "google_places"
    social_domains = {
        "twitter.com", "x.com", "instagram.com", "facebook.com", "youtube.com",
        "youtu.be", "tiktok.com",
    }
    if source_domain in social_domains:
        return "social_platform"
    return "secondary_source"


def _first_source_url(record: dict) -> str:
    raw = str(record.get("source_urls") or "").strip()
    if not raw:
        return ""
    if raw.startswith("["):
        try:
            parsed = ast.literal_eval(raw)
        except (SyntaxError, ValueError):
            parsed = []
        if parsed:
            return str(parsed[0])
    return raw.replace("\n", ";").split(";", 1)[0].strip()


def _claim_id(record_id: str, field_name: str) -> str:
    safe_field = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in field_name)
    return f"{record_id}{AUGMENTED_MARKER}{safe_field}"


def _build_row(
    record: dict,
    field_name: str,
    source_url: str,
    confidence: str,
    claim_type: str,
    validation_logic: str,
) -> dict[str, str]:
    value = str(record.get(field_name) or "").strip()
    return {
        "claim_id": _claim_id(str(record["record_id"]), field_name),
        "record_id": str(record["record_id"]),
        "field_name": field_name,
        "claim_value": value,
        "source_url": source_url,
        "source_type": _source_type(source_url, str(record.get("website_url") or "")),
        "claim_type": claim_type,
        "validation_status": "verified" if confidence else "documented",
        "confidence_score": str(record.get("validation_score") or ""),
        "evidence_snippet": f"{field_name}={value}; confidence={confidence or 'documented'}",
        "validation_logic": validation_logic,
        "reviewed_at": datetime.now(UTC).date().isoformat(),
    }


def build_augmented_rows(
    records: list[dict],
    sec_evidence_dir: Path = DEFAULT_SEC_EVIDENCE_DIR,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for record in records:
        for group in GROUPS:
            evidence_url = str(record.get(group["evidence"]) or "").strip()
            confidence = str(record.get(group["confidence"]) or "").strip()
            for field_name in group["fields"]:
                if not _nonempty(record.get(field_name)):
                    continue
                if not evidence_url or not confidence:
                    continue
                rows.append(
                    _build_row(
                        record,
                        field_name,
                        evidence_url,
                        confidence,
                        str(group["claim_type"]),
                        str(group["logic"]),
                    )
                )

        if _nonempty(record.get("sec_registered")):
            registered = str(record.get("sec_registered")).strip()
            evidence_url = str(record.get("sec_evidence_url") or "").strip()
            confidence = str(record.get("sec_confidence") or "").strip()
            if registered == "False":
                evidence_path = sec_evidence_dir / f"{record['record_id']}.json"
                evidence_url = str(evidence_path)
                confidence = "iapd_no_match_above_threshold"
            if evidence_url:
                rows.append(
                    _build_row(
                        record,
                        "sec_registered",
                        evidence_url,
                        confidence,
                        "regulatory_registration_status",
                        (
                            "SEC IAPD search completed for the record; unmatched rows "
                            "are explicit no-match findings."
                        ),
                    )
                )

        for slot in (1, 2, 3):
            src_col = f"principal_{slot}_source_url"
            conf_col = f"principal_{slot}_confidence"
            source_url = str(record.get(src_col) or "").strip()
            confidence = str(record.get(conf_col) or "").strip()
            for field_name in (f"principal_{slot}_name", f"principal_{slot}_role"):
                if _nonempty(record.get(field_name)) and source_url and confidence:
                    rows.append(
                        _build_row(
                            record,
                            field_name,
                            source_url,
                            confidence,
                            "official_team_roster",
                            "Principal slot promoted only from official team/about-page evidence.",
                        )
                    )

        if _nonempty(record.get("recent_activity")):
            source_url = (
                str(record.get("recent_activity_url") or "").strip()
                or _first_source_url(record)
            )
            confidence = (
                str(record.get("recent_activity_confidence") or "").strip()
                or "news_signal"
            )
            for field_name in (
                "recent_activity",
                "recent_activity_date",
                "recent_activity_outlet",
                "recent_activity_url",
                "recent_activity_type",
            ):
                if _nonempty(record.get(field_name)):
                    rows.append(
                        _build_row(
                            record,
                            field_name,
                            source_url,
                            confidence,
                            "recent_activity_signal",
                            (
                                "Recent activity retained only after date/source/name "
                                "filtering or existing validated promotion."
                            ),
                        )
                    )
        elif _nonempty(record.get("recent_activity_type")):
            rows.append(
                _build_row(
                    record,
                    "recent_activity_type",
                    METHODOLOGY_SOURCE,
                    str(record.get("recent_activity_confidence") or ""),
                    "no_recent_signal_status",
                    "No qualifying recent public signal survived the conservative filter.",
                )
            )

        first_source = _first_source_url(record) or METHODOLOGY_SOURCE
        for field_name, logic in DERIVED_FIELDS.items():
            if not _nonempty(record.get(field_name)):
                continue
            source_url = (
                METHODOLOGY_SOURCE
                if field_name.startswith("data_completion")
                or "secondary" in field_name
                or field_name == "email_code_explanation_secondary"
                else first_source
            )
            rows.append(
                _build_row(
                    record,
                    field_name,
                    source_url,
                    "derived_from_validated_record",
                    "derived_or_sample_parity",
                    logic,
                )
            )
    return rows


@app.command("run")
def run_augmentation(
    dataset: Annotated[Path, typer.Option("--dataset")] = DEFAULT_DATASET,
    field_evidence: Annotated[Path, typer.Option("--field-evidence")] = DEFAULT_FIELD_EVIDENCE,
    sec_evidence_dir: Annotated[
        Path, typer.Option("--sec-evidence-dir")
    ] = DEFAULT_SEC_EVIDENCE_DIR,
) -> None:
    """Append deterministic promoted-field evidence rows to field_evidence.csv."""
    if not dataset.exists():
        raise typer.BadParameter(f"dataset not found: {dataset}")
    if not field_evidence.exists():
        raise typer.BadParameter(f"field evidence not found: {field_evidence}")

    records = pd.read_csv(dataset, dtype=str).fillna("").to_dict(orient="records")
    existing = pd.read_csv(field_evidence, dtype=str).fillna("")
    if "claim_id" in existing.columns:
        existing = existing[
            ~existing["claim_id"].astype(str).str.contains(AUGMENTED_MARKER, regex=False)
        ]
    additions = pd.DataFrame(build_augmented_rows(records, sec_evidence_dir))
    output = pd.concat([existing, additions], ignore_index=True)
    output.to_csv(field_evidence, index=False)
    typer.echo(
        f"Field evidence augmented: kept={len(existing)}, added={len(additions)}, "
        f"total={len(output)}."
    )


if __name__ == "__main__":
    app()
