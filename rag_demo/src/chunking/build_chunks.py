from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import CHUNKS_PATH
from src.loaders.family_offices import clean_text, parse_source_urls, to_bool, to_int
from src.schema import Chunk, ChunkMetadata, ChunkType

REQUIRED_METADATA_KEYS = [
    "chunk_id",
    "record_id",
    "chunk_type",
    "family_office_name",
    "family_office_type",
    "country",
    "state_region",
    "city",
    "source_urls",
    "primary_source_url",
    "field_name",
    "field_value_text",
    "evidence_quality",
    "confidence_label",
    "validation_status",
    "validation_score",
    "source_count",
    "website_ok",
    "sec_registered",
    "sec_crd_number",
    "sec_confidence",
    "recent_activity_type",
    "recent_activity_date",
    "recent_activity_outlet",
    "recent_activity_confidence",
    "human_audit_status",
    "auto_prescreen_flag",
    "uncertainty_notes",
    "data_validation_period",
    "safe_answer_policy",
]

FIELD_EVIDENCE_FIELDS = [
    "website_url",
    "corporate_linkedin_url",
    "primary_email",
    "primary_phone",
    "google_places_phone",
    "street_address",
    "principal_name",
    "principal_title",
    "principal_linkedin_url",
    "contact_full_name",
    "contact_secondary_email",
    "contact_secondary_phone",
    "aum_text",
    "principal_1_name",
    "principal_1_role",
    "principal_2_name",
    "principal_2_role",
    "principal_3_name",
    "principal_3_role",
]

FIELD_URL_MAP = {
    "primary_email": "primary_email_evidence_url",
    "primary_phone": "primary_phone_evidence_url",
    "corporate_linkedin_url": "corporate_linkedin_evidence_url",
    "google_places_phone": "google_places_evidence_url",
    "street_address": "street_address_evidence_url",
    "principal_1_name": "principal_1_source_url",
    "principal_1_role": "principal_1_source_url",
    "principal_2_name": "principal_2_source_url",
    "principal_2_role": "principal_2_source_url",
    "principal_3_name": "principal_3_source_url",
    "principal_3_role": "principal_3_source_url",
}

FIELD_CONFIDENCE_MAP = {
    "primary_email": "primary_email_confidence",
    "primary_phone": "primary_phone_confidence",
    "corporate_linkedin_url": "corporate_linkedin_confidence",
    "google_places_phone": "google_places_confidence",
    "street_address": "street_address_confidence",
    "principal_1_name": "principal_1_confidence",
    "principal_1_role": "principal_1_confidence",
    "principal_2_name": "principal_2_confidence",
    "principal_2_role": "principal_2_confidence",
    "principal_3_name": "principal_3_confidence",
    "principal_3_role": "principal_3_confidence",
}


def _dedupe_urls(urls: list[str]) -> list[str]:
    return list(dict.fromkeys(url for url in urls if clean_text(url)))


def _row_urls(record: dict[str, Any]) -> list[str]:
    return parse_source_urls(record.get("source_urls"))


def _field_urls(record: dict[str, Any], field_name: str) -> list[str]:
    evidence_field = FIELD_URL_MAP.get(field_name)
    urls = parse_source_urls(record.get(evidence_field)) if evidence_field else []
    return _dedupe_urls(urls + _row_urls(record))


def _primary_url(record: dict[str, Any], chunk_type: ChunkType, field_name: str = "") -> str:
    if chunk_type == "field_evidence" and field_name:
        urls = _field_urls(record, field_name)
        return urls[0] if urls else ""
    if chunk_type == "regulatory":
        for key in ["sec_evidence_url", "sec_summary_url", "form_adv_brochure_url"]:
            value = clean_text(record.get(key))
            if value:
                return value
        if not to_bool(record.get("sec_registered")):
            return "https://adviserinfo.sec.gov/"
    if chunk_type == "recent_activity":
        value = clean_text(record.get("recent_activity_url"))
        if value:
            return value
    urls = _row_urls(record)
    return urls[0] if urls else ""


def _base_metadata(
    record: dict[str, Any],
    chunk_id: str,
    chunk_type: ChunkType,
    *,
    field_name: str = "",
    field_value_text: str = "",
    source_urls: list[str] | None = None,
    primary_source_url: str = "",
    confidence_label: str = "",
    safe_answer_policy: str = "evidence_only",
) -> ChunkMetadata:
    urls = _dedupe_urls(source_urls if source_urls is not None else _row_urls(record))
    return ChunkMetadata(
        chunk_id=chunk_id,
        record_id=clean_text(record.get("record_id")),
        chunk_type=chunk_type,
        family_office_name=clean_text(record.get("family_office_name")),
        family_office_type=clean_text(record.get("family_office_type")),
        country=clean_text(record.get("country")),
        state_region=clean_text(record.get("state_region")),
        city=clean_text(record.get("city")),
        source_urls=urls,
        primary_source_url=primary_source_url or _primary_url(record, chunk_type, field_name),
        field_name=field_name,
        field_value_text=field_value_text,
        evidence_quality=clean_text(record.get("evidence_quality")),
        confidence_label=confidence_label or clean_text(record.get("confidence")),
        validation_status=clean_text(record.get("validation_status")),
        validation_score=to_int(record.get("validation_score")),
        source_count=to_int(record.get("source_count")),
        website_ok=to_bool(record.get("website_ok")),
        sec_registered=to_bool(record.get("sec_registered")),
        sec_crd_number=clean_text(record.get("sec_crd_number")),
        sec_confidence=clean_text(record.get("sec_confidence")),
        recent_activity_type=clean_text(record.get("recent_activity_type")),
        recent_activity_date=clean_text(record.get("recent_activity_date")),
        recent_activity_outlet=clean_text(record.get("recent_activity_outlet")),
        recent_activity_confidence=clean_text(record.get("recent_activity_confidence")),
        human_audit_status=clean_text(record.get("human_audit_status")),
        auto_prescreen_flag=clean_text(record.get("auto_prescreen_flag")),
        uncertainty_notes=clean_text(record.get("uncertainty_notes")),
        data_validation_period=clean_text(record.get("data_validation_period")),
        safe_answer_policy=safe_answer_policy,
    )


def _join_lines(lines: list[str]) -> str:
    return "\n".join(line for line in lines if clean_text(line))


def _not_evidenced(value: Any) -> str:
    return clean_text(value) if clean_text(value) else "not evidenced in the locked dataset"


def _profile_chunk(record: dict[str, Any]) -> Chunk:
    chunk_id = f"{record['record_id']}::record_profile"
    text = _join_lines(
        [
            f"Record profile for {clean_text(record.get('family_office_name'))}.",
            f"Record ID: {clean_text(record.get('record_id'))}.",
            f"Family office type: {_not_evidenced(record.get('family_office_type'))}.",
            (
                "Location: "
                f"{_not_evidenced(record.get('city'))}, "
                f"{_not_evidenced(record.get('state_region'))}, "
                f"{_not_evidenced(record.get('country'))}."
            ),
            f"Description: {_not_evidenced(record.get('description'))}.",
            f"Investment thesis: {_not_evidenced(record.get('investment_thesis'))}.",
            f"Investing sectors: {_not_evidenced(record.get('investing_sectors'))}.",
            f"Website: {_not_evidenced(record.get('website_url'))}.",
            f"Corporate LinkedIn: {_not_evidenced(record.get('corporate_linkedin_url'))}.",
            f"Source notes: {_not_evidenced(record.get('source_notes'))}.",
            f"Confidence: {_not_evidenced(record.get('confidence'))}.",
            f"Uncertainty notes: {_not_evidenced(record.get('uncertainty_notes'))}.",
        ]
    )
    return Chunk(
        chunk_id=chunk_id,
        text=text,
        metadata=_base_metadata(record, chunk_id, "record_profile"),
    )


def _contact_policy_chunk(record: dict[str, Any]) -> Chunk:
    chunk_id = f"{record['record_id']}::contact_policy"
    text = _join_lines(
        [
            f"Contact policy for {clean_text(record.get('family_office_name'))}.",
            "Safe answer policy: return only values directly evidenced in this locked dataset; "
            "if a contact, principal LinkedIn, or AUM field is blank, say it is not evidenced.",
            f"Primary email: {_not_evidenced(record.get('primary_email'))}.",
            f"Primary email evidence URL: {_not_evidenced(record.get('primary_email_evidence_url'))}.",
            f"Primary email confidence: {_not_evidenced(record.get('primary_email_confidence'))}.",
            f"Primary phone: {_not_evidenced(record.get('primary_phone'))}.",
            f"Primary phone evidence URL: {_not_evidenced(record.get('primary_phone_evidence_url'))}.",
            f"Primary phone confidence: {_not_evidenced(record.get('primary_phone_confidence'))}.",
            f"Principal name: {_not_evidenced(record.get('principal_name'))}.",
            f"Principal title: {_not_evidenced(record.get('principal_title'))}.",
            f"Principal LinkedIn: {_not_evidenced(record.get('principal_linkedin_url'))}.",
            f"AUM: {_not_evidenced(record.get('aum_text'))}.",
            f"Secondary contact email: {_not_evidenced(record.get('contact_secondary_email'))}.",
            f"Secondary contact phone: {_not_evidenced(record.get('contact_secondary_phone'))}.",
            f"Uncertainty notes: {_not_evidenced(record.get('uncertainty_notes'))}.",
        ]
    )
    contact_urls = _dedupe_urls(
        parse_source_urls(record.get("primary_email_evidence_url"))
        + parse_source_urls(record.get("primary_phone_evidence_url"))
        + _row_urls(record)
    )
    return Chunk(
        chunk_id=chunk_id,
        text=text,
        metadata=_base_metadata(
            record,
            chunk_id,
            "contact_policy",
            source_urls=contact_urls,
            primary_source_url=contact_urls[0] if contact_urls else "",
            safe_answer_policy="sensitive_fields_require_direct_evidence",
        ),
    )


def _regulatory_chunk(record: dict[str, Any]) -> Chunk:
    chunk_id = f"{record['record_id']}::regulatory"
    sec_registered = to_bool(record.get("sec_registered"))
    text = _join_lines(
        [
            f"Regulatory evidence for {clean_text(record.get('family_office_name'))}.",
            f"SEC registered: {'true' if sec_registered else 'false'}.",
            f"SEC CRD number: {_not_evidenced(record.get('sec_crd_number'))}.",
            f"SEC file number: {_not_evidenced(record.get('sec_file_number'))}.",
            f"SEC registration status: {_not_evidenced(record.get('sec_registration_status'))}.",
            f"SEC firm name from IAPD: {_not_evidenced(record.get('sec_firm_name_iapd'))}.",
            f"SEC other names: {_not_evidenced(record.get('sec_firm_other_names'))}.",
            f"SEC branches count: {_not_evidenced(record.get('sec_branches_count'))}.",
            f"SEC summary URL: {_not_evidenced(record.get('sec_summary_url'))}.",
            f"SEC evidence URL: {_not_evidenced(record.get('sec_evidence_url'))}.",
            f"Form ADV brochure URL: {_not_evidenced(record.get('form_adv_brochure_url'))}.",
            f"SEC address: {_not_evidenced(record.get('sec_address_city'))}, "
            f"{_not_evidenced(record.get('sec_address_state'))}, "
            f"{_not_evidenced(record.get('sec_address_country'))}.",
            f"SEC confidence: {_not_evidenced(record.get('sec_confidence'))}.",
            f"Uncertainty notes: {_not_evidenced(record.get('uncertainty_notes'))}.",
        ]
    )
    urls = _dedupe_urls(
        parse_source_urls(record.get("sec_evidence_url"))
        + parse_source_urls(record.get("sec_summary_url"))
        + parse_source_urls(record.get("form_adv_brochure_url"))
        + _row_urls(record)
    )
    if not sec_registered:
        urls = _dedupe_urls(["https://adviserinfo.sec.gov/", *urls])
    return Chunk(
        chunk_id=chunk_id,
        text=text,
        metadata=_base_metadata(
            record,
            chunk_id,
            "regulatory",
            source_urls=urls,
            primary_source_url=urls[0] if urls else "",
            confidence_label=clean_text(record.get("sec_confidence")) or clean_text(record.get("confidence")),
            safe_answer_policy="sec_claims_require_regulatory_chunk",
        ),
    )


def _recent_activity_chunk(record: dict[str, Any]) -> Chunk | None:
    has_recent = any(
        clean_text(record.get(key))
        for key in [
            "recent_activity",
            "recent_activity_date",
            "recent_activity_outlet",
            "recent_activity_url",
        ]
    )
    if not has_recent:
        return None
    chunk_id = f"{record['record_id']}::recent_activity"
    text = _join_lines(
        [
            f"Recent activity evidence for {clean_text(record.get('family_office_name'))}.",
            f"Recent activity: {_not_evidenced(record.get('recent_activity'))}.",
            f"Recent activity date: {_not_evidenced(record.get('recent_activity_date'))}.",
            f"Recent activity outlet: {_not_evidenced(record.get('recent_activity_outlet'))}.",
            f"Recent activity type: {_not_evidenced(record.get('recent_activity_type'))}.",
            f"Recent activity URL: {_not_evidenced(record.get('recent_activity_url'))}.",
            f"Recent activity confidence: {_not_evidenced(record.get('recent_activity_confidence'))}.",
            f"Uncertainty notes: {_not_evidenced(record.get('uncertainty_notes'))}.",
        ]
    )
    urls = _dedupe_urls(parse_source_urls(record.get("recent_activity_url")) + _row_urls(record))
    return Chunk(
        chunk_id=chunk_id,
        text=text,
        metadata=_base_metadata(
            record,
            chunk_id,
            "recent_activity",
            source_urls=urls,
            primary_source_url=urls[0] if urls else "",
            confidence_label=clean_text(record.get("recent_activity_confidence"))
            or clean_text(record.get("confidence")),
            safe_answer_policy="recent_activity_requires_activity_chunk",
        ),
    )


def _field_evidence_chunks(record: dict[str, Any]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for field_name in FIELD_EVIDENCE_FIELDS:
        value = clean_text(record.get(field_name))
        if not value:
            continue
        chunk_id = f"{record['record_id']}::field_evidence::{field_name}"
        confidence_field = FIELD_CONFIDENCE_MAP.get(field_name, "")
        confidence = clean_text(record.get(confidence_field)) if confidence_field else clean_text(
            record.get("confidence")
        )
        urls = _field_urls(record, field_name)
        text = _join_lines(
            [
                f"Field evidence for {clean_text(record.get('family_office_name'))}.",
                f"Field name: {field_name}.",
                f"Field value: {value}.",
                f"Evidence URL: {_not_evidenced(urls[0] if urls else '')}.",
                f"Evidence confidence: {_not_evidenced(confidence)}.",
                "Safe answer policy: use this field value only as written; do not infer adjacent "
                "contact, AUM, regulatory, or recent activity facts.",
            ]
        )
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                text=text,
                metadata=_base_metadata(
                    record,
                    chunk_id,
                    "field_evidence",
                    field_name=field_name,
                    field_value_text=value,
                    source_urls=urls,
                    primary_source_url=urls[0] if urls else "",
                    confidence_label=confidence,
                    safe_answer_policy="field_value_exact_extract_only",
                ),
            )
        )
    return chunks


def build_chunks(records: list[dict[str, Any]]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for record in records:
        if clean_text(record.get("validation_status")).lower() not in {"accepted", "valid", "validated"}:
            continue
        chunks.append(_profile_chunk(record))
        chunks.append(_contact_policy_chunk(record))
        chunks.append(_regulatory_chunk(record))
        recent_chunk = _recent_activity_chunk(record)
        if recent_chunk is not None:
            chunks.append(recent_chunk)
        chunks.extend(_field_evidence_chunks(record))
    return chunks


def write_chunks(chunks: list[Chunk], path: Path = CHUNKS_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for chunk in chunks:
            file.write(chunk.model_dump_json() + "\n")
    return path


def load_chunks(path: Path = CHUNKS_PATH) -> list[Chunk]:
    if not path.exists():
        raise FileNotFoundError(f"Chunk file not found at {path}. Run scripts/build_all.py first.")
    chunks: list[Chunk] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                chunks.append(Chunk.model_validate_json(line))
            except ValueError as exc:
                raise ValueError(f"Invalid chunk JSON on line {line_number}: {exc}") from exc
    return chunks


def build_chunks_file(records: list[dict[str, Any]], path: Path = CHUNKS_PATH) -> list[Chunk]:
    chunks = build_chunks(records)
    write_chunks(chunks, path)
    return chunks


def metadata_key_coverage(chunks: list[Chunk]) -> dict[str, bool]:
    return {
        key: all(key in chunk.metadata.model_dump() for chunk in chunks)
        for key in REQUIRED_METADATA_KEYS
    }


def chunks_to_json(chunks: list[Chunk]) -> str:
    return json.dumps([chunk.model_dump(mode="json") for chunk in chunks], indent=2)
