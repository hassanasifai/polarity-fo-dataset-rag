from __future__ import annotations

from collections import defaultdict
from typing import Any

from src.loaders.family_offices import clean_text, load_family_offices, parse_source_urls, to_bool
from src.retrieval.hybrid import retrieve
from src.schema import AnswerCitation, AnswerResult, RetrievalHit, RetrievalResult

SENSITIVE_MISSING_TEXT = "not evidenced in the locked dataset"


def _records_by_id() -> dict[str, dict[str, Any]]:
    return {clean_text(record.get("record_id")): record for record in load_family_offices()}


def _source_urls_from_metadata(metadata: dict[str, Any]) -> list[str]:
    value = metadata.get("source_urls", [])
    if isinstance(value, list):
        urls = [clean_text(item) for item in value if clean_text(item)]
    else:
        urls = parse_source_urls(value)
    primary = clean_text(metadata.get("primary_source_url"))
    if primary:
        urls.insert(0, primary)
    return list(dict.fromkeys(urls))


def _citation_for_hit(hit: RetrievalHit, field_name: str = "") -> AnswerCitation | None:
    urls = _source_urls_from_metadata(hit.metadata)
    if not urls:
        return None
    return AnswerCitation(
        record_id=hit.record_id,
        family_office_name=clean_text(hit.metadata.get("family_office_name")),
        chunk_id=hit.chunk_id,
        chunk_type=hit.chunk_type,
        source_url=urls[0],
        field_name=field_name or clean_text(hit.metadata.get("field_name")),
    )


def _first_citation(hits: list[RetrievalHit], preferred_types: set[str] | None = None) -> AnswerCitation | None:
    for hit in hits:
        if preferred_types and hit.chunk_type not in preferred_types:
            continue
        citation = _citation_for_hit(hit)
        if citation:
            return citation
    for hit in hits:
        citation = _citation_for_hit(hit)
        if citation:
            return citation
    return None


def _group_hits(hits: list[RetrievalHit]) -> dict[str, list[RetrievalHit]]:
    grouped: dict[str, list[RetrievalHit]] = defaultdict(list)
    for hit in hits:
        grouped[hit.record_id].append(hit)
    return dict(grouped)


def _record_hits(result: RetrievalResult, record_id: str) -> list[RetrievalHit]:
    return [hit for hit in result.hits if hit.record_id == record_id]


def _field_value(record: dict[str, Any], field_name: str) -> str:
    return clean_text(record.get(field_name))


def _contact_field_label(field_name: str) -> str:
    return {
        "primary_email": "primary email",
        "primary_phone": "primary phone",
        "principal_linkedin_url": "principal LinkedIn",
        "aum_text": "AUM",
    }.get(field_name, field_name)


def _sensitive_requested_fields(result: RetrievalResult) -> list[str]:
    fields = [
        field
        for field in result.intent.requested_fields
        if field in {"primary_email", "primary_phone", "principal_linkedin_url", "aum_text"}
    ]
    query_text = result.query.lower()
    if "principal" in query_text or "personal" in query_text or "direct" in query_text:
        if "email" in query_text and "principal_email" not in fields:
            fields.append("principal_email")
        if "phone" in query_text and "principal_phone" not in fields:
            fields.append("principal_phone")
    return list(dict.fromkeys(fields))


def _missing_answer(
    reason: str,
    result: RetrievalResult,
    *,
    confidence: str = "low",
    citations: list[AnswerCitation] | None = None,
    missing_data: list[str] | None = None,
) -> AnswerResult:
    caveats = [
        "Answers are limited to the locked validated dataset; no live web lookup or model prior was used."
    ]
    if result.intent.filters:
        caveats.append(f"Applied parsed filters: {result.intent.filters}.")
    return AnswerResult(
        answer=reason,
        confidence=confidence,  # type: ignore[arg-type]
        abstain=True,
        caveats=caveats,
        missing_data=missing_data or [reason],
        citations=citations or [],
        unsupported_claim_count=0,
    )


def _contact_answer(result: RetrievalResult, records: dict[str, dict[str, Any]]) -> AnswerResult:
    query_text = result.query.lower()
    asks_principal_personal_contact = (
        any(term in query_text for term in ["principal", "personal", "private", "direct"])
        and any(term in query_text for term in ["email", "phone", "cell", "mobile"])
    )
    if not result.intent.matched_record_ids:
        if asks_principal_personal_contact:
            return _missing_answer(
                "Principal-level personal contact details are not evidenced for a matched record in the locked dataset.",
                result,
                missing_data=["principal email/phone/LinkedIn: not evidenced in the locked dataset."],
            )
        if any(
            field in result.intent.requested_fields
            for field in ["primary_email", "primary_phone", "principal_linkedin_url", "aum_text"]
        ):
            return _missing_answer(
                "No matching family-office record was found for the requested sensitive field, so the system abstained.",
                result,
                missing_data=["Sensitive fields require an exact matched record and direct dataset evidence."],
            )

    record_id = result.intent.matched_record_ids[0] if result.intent.matched_record_ids else (
        result.hits[0].record_id if result.hits else ""
    )
    if not record_id or record_id not in records:
        return _missing_answer("No matching family-office record was found in the locked dataset.", result)

    record = records[record_id]
    hits = _record_hits(result, record_id)
    citation = _first_citation(hits, {"contact_policy", "field_evidence", "record_profile"})
    citations = [citation] if citation else []
    if asks_principal_personal_contact:
        missing = []
        if "email" in query_text:
            missing.append(f"principal email: {SENSITIVE_MISSING_TEXT}.")
        if any(term in query_text for term in ["phone", "cell", "mobile"]):
            missing.append(f"principal phone: {SENSITIVE_MISSING_TEXT}.")
        return _missing_answer(
            f"For {clean_text(record.get('family_office_name'))}, principal-level personal contact details are "
            f"{SENSITIVE_MISSING_TEXT}.",
            result,
            citations=citations,
            missing_data=missing or [f"principal contact details: {SENSITIVE_MISSING_TEXT}."],
        )

    requested_fields = _sensitive_requested_fields(result) or ["primary_email", "primary_phone"]

    facts: list[str] = []
    missing: list[str] = []
    for field_name in requested_fields:
        if field_name in {"principal_email", "principal_phone"}:
            label = field_name.replace("_", " ")
            missing.append(f"{label}: {SENSITIVE_MISSING_TEXT}.")
            continue
        value = _field_value(record, field_name)
        label = _contact_field_label(field_name)
        if value:
            facts.append(f"{label}: {value}")
        else:
            missing.append(f"{label}: {SENSITIVE_MISSING_TEXT}.")

    name = clean_text(record.get("family_office_name"))
    if not facts:
        return _missing_answer(
            f"For {name}, the requested sensitive field(s) are {SENSITIVE_MISSING_TEXT}.",
            result,
            citations=citations,
            missing_data=missing,
        )

    answer = f"For {name}, the locked dataset lists " + "; ".join(facts) + "."
    caveats = [
        "Sensitive contact and AUM fields are copied only when directly present in the validated dataset.",
        "Blank sensitive fields are not inferred from websites, names, or model knowledge.",
    ]
    return AnswerResult(
        answer=answer,
        confidence="high" if citations else "medium",
        abstain=False,
        caveats=caveats,
        missing_data=missing,
        citations=citations,
        unsupported_claim_count=0,
    )


def _regulatory_answer(result: RetrievalResult, records: dict[str, dict[str, Any]]) -> AnswerResult:
    target_ids = result.intent.matched_record_ids or [hit.record_id for hit in result.hits[:1]]
    if not target_ids:
        return _missing_answer("No matching regulatory evidence was retrieved from the locked dataset.", result)

    lines: list[str] = []
    citations: list[AnswerCitation] = []
    caveats = ["SEC statements reflect the locked validation snapshot, not a live legal determination."]
    for record_id in list(dict.fromkeys(target_ids))[:5]:
        record = records.get(record_id)
        if not record:
            continue
        hits = _record_hits(result, record_id)
        citation = _first_citation(hits, {"regulatory"})
        if citation:
            citations.append(citation)
        name = clean_text(record.get("family_office_name"))
        registered = to_bool(record.get("sec_registered"))
        crd = _field_value(record, "sec_crd_number")
        status = _field_value(record, "sec_registration_status")
        confidence = _field_value(record, "sec_confidence")
        if registered:
            details = [f"{name} is marked SEC-registered in the locked dataset"]
            if crd:
                details.append(f"CRD {crd}")
            if status:
                details.append(f"status {status}")
            if confidence:
                details.append(f"confidence {confidence}")
            lines.append(", ".join(details) + ".")
        else:
            lines.append(
                f"{name} is not shown as SEC-registered in the locked dataset as of the validation snapshot."
            )

    if not lines:
        return _missing_answer("No usable regulatory record was found after retrieval.", result)
    return AnswerResult(
        answer=" ".join(lines),
        confidence="high" if citations else "medium",
        abstain=False,
        caveats=caveats,
        missing_data=[],
        citations=citations,
        unsupported_claim_count=0,
    )


def _recent_activity_answer(result: RetrievalResult, records: dict[str, dict[str, Any]]) -> AnswerResult:
    record_id = result.intent.matched_record_ids[0] if result.intent.matched_record_ids else (
        result.hits[0].record_id if result.hits else ""
    )
    if not record_id or record_id not in records:
        return _missing_answer("No matching record was found for recent-activity lookup.", result)

    record = records[record_id]
    hits = _record_hits(result, record_id)
    citation = _first_citation(hits, {"recent_activity"})
    citations = [citation] if citation else []
    activity = _field_value(record, "recent_activity")
    date = _field_value(record, "recent_activity_date")
    outlet = _field_value(record, "recent_activity_outlet")
    activity_type = _field_value(record, "recent_activity_type")
    name = clean_text(record.get("family_office_name"))
    if not activity and not date:
        return _missing_answer(
            f"For {name}, recent activity is {SENSITIVE_MISSING_TEXT}.",
            result,
            citations=citations,
            missing_data=[f"recent activity: {SENSITIVE_MISSING_TEXT}."],
        )
    details = [f"For {name}, the locked dataset records recent activity"]
    if date:
        details.append(f"dated {date}")
    if outlet:
        details.append(f"from {outlet}")
    if activity_type:
        details.append(f"type {activity_type}")
    answer = ", ".join(details) + f": {activity or SENSITIVE_MISSING_TEXT}."
    return AnswerResult(
        answer=answer,
        confidence="high" if citations else "medium",
        abstain=False,
        caveats=["Recent-activity answers are snapshot-bound and do not claim to be live news."],
        missing_data=[],
        citations=citations,
        unsupported_claim_count=0,
    )


def _filtered_listing_answer(result: RetrievalResult, records: dict[str, dict[str, Any]]) -> AnswerResult:
    grouped = _group_hits(result.hits)
    record_ids = list(grouped.keys())
    if not record_ids:
        return _missing_answer("No records matched the requested filters in the retrieved evidence.", result)

    lines: list[str] = []
    citations: list[AnswerCitation] = []
    for record_id in record_ids[:10]:
        record = records.get(record_id)
        if not record:
            continue
        citation = _first_citation(grouped[record_id])
        if citation:
            citations.append(citation)
        location = ", ".join(
            part
            for part in [
                _field_value(record, "city"),
                _field_value(record, "state_region"),
                _field_value(record, "country"),
            ]
            if part
        )
        sec = "SEC-registered" if to_bool(record.get("sec_registered")) else "not shown SEC-registered"
        lines.append(f"{record['family_office_name']} ({record_id}) - {location}; {sec}.")

    if not lines:
        return _missing_answer("Records were retrieved, but none could be rendered safely.", result)
    return AnswerResult(
        answer="\n".join(lines),
        confidence="medium",
        abstain=False,
        caveats=[
            "Filtered listings are limited to records surfaced from the local indexes and parsed metadata filters."
        ],
        missing_data=[],
        citations=citations,
        unsupported_claim_count=0,
    )


def _comparison_answer(result: RetrievalResult, records: dict[str, dict[str, Any]]) -> AnswerResult:
    record_ids = result.intent.matched_record_ids or list(_group_hits(result.hits).keys())[:2]
    if len(record_ids) < 2:
        return _missing_answer("Comparison requires at least two matching records in the locked dataset.", result)
    grouped = _group_hits(result.hits)
    lines: list[str] = []
    citations: list[AnswerCitation] = []
    missing: list[str] = []
    for record_id in record_ids[:4]:
        record = records.get(record_id)
        if not record:
            continue
        citation = _first_citation(grouped.get(record_id, []))
        if citation:
            citations.append(citation)
        name = clean_text(record.get("family_office_name"))
        email_state = "email evidenced" if _field_value(record, "primary_email") else "email not evidenced"
        phone_state = "phone evidenced" if _field_value(record, "primary_phone") else "phone not evidenced"
        if not _field_value(record, "primary_email"):
            missing.append(f"{name}: primary email {SENSITIVE_MISSING_TEXT}.")
        if not _field_value(record, "primary_phone"):
            missing.append(f"{name}: primary phone {SENSITIVE_MISSING_TEXT}.")
        location = ", ".join(
            part
            for part in [
                _field_value(record, "city"),
                _field_value(record, "state_region"),
                _field_value(record, "country"),
            ]
            if part
        )
        sec = (
            f"SEC-registered, CRD {_field_value(record, 'sec_crd_number')}"
            if to_bool(record.get("sec_registered"))
            else "not shown SEC-registered"
        )
        lines.append(
            f"{name} ({record_id}): type {_field_value(record, 'family_office_type') or SENSITIVE_MISSING_TEXT}; "
            f"location {location or SENSITIVE_MISSING_TEXT}; {sec}; contact availability: {email_state}, {phone_state}."
        )
    return AnswerResult(
        answer="\n".join(lines),
        confidence="medium",
        abstain=False,
        caveats=["Comparison uses only selected fields from the locked dataset."],
        missing_data=missing,
        citations=citations,
        unsupported_claim_count=0,
    )


def _entity_lookup_answer(result: RetrievalResult, records: dict[str, dict[str, Any]]) -> AnswerResult:
    if not result.intent.matched_record_ids:
        return _missing_answer("No matching family-office record was found in the locked dataset.", result)
    record_id = result.intent.matched_record_ids[0] if result.intent.matched_record_ids else (
        result.hits[0].record_id if result.hits else ""
    )
    if not record_id or record_id not in records:
        return _missing_answer("No matching family-office record was found in the locked dataset.", result)
    record = records[record_id]
    hits = _record_hits(result, record_id)
    citation = _first_citation(hits, {"record_profile", "field_evidence"})
    citations = [citation] if citation else []
    location = ", ".join(
        part
        for part in [
            _field_value(record, "city"),
            _field_value(record, "state_region"),
            _field_value(record, "country"),
        ]
        if part
    )
    answer = (
        f"{record['family_office_name']} ({record_id}) is classified as "
        f"{_field_value(record, 'family_office_type') or SENSITIVE_MISSING_TEXT}"
        f" and is based in {location or SENSITIVE_MISSING_TEXT}."
    )
    description = _field_value(record, "description")
    if description:
        answer += f" Dataset description: {description}"
    return AnswerResult(
        answer=answer,
        confidence="high" if citations else "medium",
        abstain=False,
        caveats=["Profile answers are limited to validated row fields and cited source notes."],
        missing_data=[],
        citations=citations,
        unsupported_claim_count=0,
    )


def answer_from_retrieval(result: RetrievalResult) -> AnswerResult:
    if not result.hits:
        return _missing_answer("No evidence was retrieved from the locked dataset.", result)

    records = _records_by_id()
    if result.intent.intent == "contact_lookup":
        return _contact_answer(result, records)
    if result.intent.intent == "regulatory":
        return _regulatory_answer(result, records)
    if result.intent.intent == "recent_activity":
        return _recent_activity_answer(result, records)
    if result.intent.intent == "filtered_listing":
        return _filtered_listing_answer(result, records)
    if result.intent.intent == "comparison":
        return _comparison_answer(result, records)
    return _entity_lookup_answer(result, records)


def ask(query: str, *, top_k: int = 10, use_reranker: bool = False) -> tuple[RetrievalResult, AnswerResult]:
    result = retrieve(query, top_k=top_k, use_reranker=use_reranker)
    return result, answer_from_retrieval(result)
