from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from src.answering.deterministic import answer_from_retrieval
from src.answering.local_llm import rewrite_with_local_llm
from src.config import DEMO_QUERIES, MANIFEST_PATH
from src.loaders.family_offices import clean_text, load_family_offices, parse_source_urls, to_bool
from src.retrieval.hybrid import retrieve
from src.schema import AnswerResult, RetrievalHit, RetrievalResult

st.set_page_config(page_title="PolarityIQ Evidence Review", layout="wide")

NOT_EVIDENCED = "not evidenced in the locked dataset"
EVAL_KEYS = [
    "hit_at_3",
    "MRR",
    "record_recall_at_5",
    "citation_accuracy",
    "abstention_accuracy",
    "missing_data_honesty",
]


def _load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _load_eval_summary() -> dict[str, float]:
    report_path = ROOT / "reports" / "eval_report.md"
    if not report_path.exists():
        return {}

    summary: dict[str, float] = {}
    for line in report_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text.startswith("- ") or ":" not in text:
            continue
        key, value = text[2:].split(":", 1)
        try:
            summary[key.strip()] = float(value.strip())
        except ValueError:
            continue
    return summary


def _records_by_id() -> dict[str, dict[str, Any]]:
    return {clean_text(record.get("record_id")): record for record in load_family_offices()}


def _domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or parsed.path or url


def _coerce_urls(value: Any) -> list[str]:
    if isinstance(value, list):
        return [clean_text(item) for item in value if clean_text(item)]
    text = clean_text(value)
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return parse_source_urls(text)
        if isinstance(parsed, list):
            return [clean_text(item) for item in parsed if clean_text(item)]
    return parse_source_urls(text)


def _source_urls_from_metadata(metadata: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    primary = clean_text(metadata.get("primary_source_url"))
    if primary:
        urls.append(primary)
    urls.extend(_coerce_urls(metadata.get("source_urls")))
    return list(dict.fromkeys(url for url in urls if url))


def _source_urls_from_record(record: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    primary = clean_text(record.get("primary_source_url"))
    if primary:
        urls.append(primary)
    urls.extend(_coerce_urls(record.get("source_urls")))
    website = clean_text(record.get("website_url"))
    if website:
        urls.append(website)
    return list(dict.fromkeys(url for url in urls if url))


def _source_urls(hit: RetrievalHit) -> list[str]:
    return _source_urls_from_metadata(hit.metadata)


def _deduped_domain_links(urls: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen_domains: set[str] = set()
    for url in urls:
        domain = _domain(url)
        key = domain.lower()
        if not key or key in seen_domains:
            continue
        seen_domains.add(key)
        rows.append({"Source Domain": domain, "URL": url})
    return rows


def _source_domain_text(urls: list[str]) -> str:
    domains = [row["Source Domain"] for row in _deduped_domain_links(urls)]
    return ", ".join(domains) if domains else "-"


def _why(hit: RetrievalHit) -> str:
    labels = {
        "exact_record_match": "Exact match",
        "dense+bm25": "Dense + BM25",
        "metadata_filter_match": "Metadata filter",
        "dense": "Dense retrieval",
        "bm25": "BM25 lexical",
    }
    return labels.get(hit.why_retrieved, hit.why_retrieved or "Retrieved")


def _short_text(value: Any, fallback: str = "-") -> str:
    text = clean_text(value)
    return text if text else fallback


def _field_or_missing(record: dict[str, Any], field_name: str) -> str:
    return _short_text(record.get(field_name), NOT_EVIDENCED)


def _location(record: dict[str, Any]) -> str:
    return _short_text(
        ", ".join(
            part
            for part in [
                clean_text(record.get("city")),
                clean_text(record.get("state_region")),
                clean_text(record.get("country")),
            ]
            if part
        ),
        NOT_EVIDENCED,
    )


def _hits_by_record(hits: list[RetrievalHit]) -> dict[str, list[RetrievalHit]]:
    grouped: dict[str, list[RetrievalHit]] = defaultdict(list)
    for hit in hits:
        grouped[hit.record_id].append(hit)
    return dict(grouped)


def _selected_record_ids(result: RetrievalResult, answer: AnswerResult) -> list[str]:
    if result.intent.intent == "filtered_listing":
        return list(dict.fromkeys(hit.record_id for hit in result.hits if hit.record_id))

    record_ids: list[str] = []
    record_ids.extend(result.intent.matched_record_ids)
    record_ids.extend(citation.record_id for citation in answer.citations)
    if result.intent.intent == "comparison":
        record_ids.extend(hit.record_id for hit in result.hits)
    if not record_ids and result.hits:
        record_ids.append(result.hits[0].record_id)
    return list(dict.fromkeys(record_id for record_id in record_ids if record_id))


def _record_hits(result: RetrievalResult, record_id: str) -> list[RetrievalHit]:
    return [hit for hit in result.hits if hit.record_id == record_id]


def _record_confidence(record: dict[str, Any], hits: list[RetrievalHit], answer: AnswerResult) -> str:
    for hit in hits:
        confidence = clean_text(hit.metadata.get("confidence_label"))
        if confidence:
            return confidence
    score = clean_text(record.get("validation_score"))
    if score:
        return f"validation score {score}"
    return answer.confidence


def _record_source(record: dict[str, Any], hits: list[RetrievalHit]) -> str:
    urls: list[str] = []
    for hit in hits:
        urls.extend(_source_urls(hit))
    urls.extend(_source_urls_from_record(record))
    return _source_domain_text(list(dict.fromkeys(urls)))


def _demo_query_metadata() -> dict[str, dict[str, str]]:
    return {
        "What type of family office is Cat Trail Capital and where is it based?": {
            "category": "Entity",
            "why": "Tests exact entity matching, profile fields, confidence, and source grounding.",
        },
        "Show me the evidence for Ohana Advisors' SEC registration.": {
            "category": "SEC",
            "why": "Tests regulatory evidence, CRD display, and SEC citation discipline.",
        },
        "Do we have a direct phone number for Ralph Family Office?": {
            "category": "Contact Missingness",
            "why": "Tests abstention when a sensitive contact field is blank.",
        },
        "What recent activity is recorded for Pathstone?": {
            "category": "Recent Activity",
            "why": "Tests dated activity, outlet, and snapshot-bound sourcing.",
        },
        "Which SEC-registered family offices in California are in the dataset?": {
            "category": "Filtered Listing",
            "why": "Tests metadata filters and record table output.",
        },
        "Compare Cat Trail Capital and Ohana Advisors on type, geography, SEC status, and contact availability.": {
            "category": "Comparison",
            "why": "Tests side-by-side record comparison without filling missing fields.",
        },
        "What is the AUM of Cat Trail Capital?": {
            "category": "Negative Test",
            "why": "Tests that missing AUM is shown as absent rather than inferred.",
        },
    }


def _demo_query_groups() -> dict[str, list[str]]:
    metadata = _demo_query_metadata()
    grouped: dict[str, list[str]] = defaultdict(list)
    for query in DEMO_QUERIES:
        category = metadata.get(query, {}).get("category", "Other")
        grouped[category].append(query)
    return dict(grouped)


def _render_manifest_summary(manifest: dict[str, Any]) -> None:
    eval_summary = _load_eval_summary()
    eval_values = [eval_summary[key] for key in EVAL_KEYS if key in eval_summary]
    eval_score = f"{mean(eval_values):.3f}" if eval_values else "-"
    dataset_hash = clean_text(manifest.get("dataset_sha256"))

    with st.container(border=True):
        st.subheader("System Readiness")
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        col1.metric("Records", manifest.get("row_count", "-"))
        col2.metric("Chunks", manifest.get("chunk_count", "-"))
        col3.metric("Eval Score", eval_score)
        col4.metric("Local Only", "Yes" if manifest.get("local_only") else "No")
        col5.metric("Paid APIs", "No" if not manifest.get("paid_api_required") else "Yes")
        col6.metric("Dataset Hash", f"{dataset_hash[:10]}..." if dataset_hash else "-")
        st.caption(f"Locked dataset SHA-256: {dataset_hash or '-'}")


def _render_control_panel(manifest: dict[str, Any]) -> tuple[str, str, int, bool, bool]:
    groups = _demo_query_groups()
    categories = list(groups)
    metadata = _demo_query_metadata()

    with st.container(border=True):
        st.subheader("Query Controls")
        selected_category = st.selectbox("Demo category", categories)
        selected_query = st.selectbox("Demo query", groups[selected_category])
        details = metadata.get(selected_query, {})
        st.caption(f"Why this demo matters: {details.get('why', 'Tests evidence-grounded answering.')}")
        query = st.text_area("Question", value=selected_query, height=130)
        mode = st.radio(
            "Answer mode",
            ["safe_extract", "local_llm"],
            format_func=lambda value: {
                "safe_extract": "Safe extract",
                "local_llm": "Local LLM rewrite",
            }[value],
        )
        use_reranker = st.toggle("Local reranker", value=False)
        top_k = st.slider("Evidence chunks", min_value=5, max_value=20, value=8)
        run = st.button("Run Evidence Review", type="primary", use_container_width=True)

    with st.expander("Manifest Details", expanded=False):
        st.write(f"JSON rows: `{manifest.get('row_count')}`")
        st.write(f"XLSX rows: `{manifest.get('xlsx_rows')}`")
        st.write(f"Chunk types: `{manifest.get('chunk_type_counts')}`")
        st.write(f"BM25 chunks: `{manifest.get('bm25_index', {}).get('chunk_count')}`")
        st.write(f"Chroma chunks: `{manifest.get('dense_index', {}).get('chunk_count')}`")
        st.write(f"Embedding model: `{manifest.get('dense_index', {}).get('embedding_model', '-')}`")

    return query, mode, top_k, use_reranker, run


def _render_fact_pairs(title: str, rows: list[tuple[str, str]]) -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        for label, value in rows:
            left, right = st.columns([1, 2])
            left.write(label)
            right.write(value)


def _render_missing_fields(answer: AnswerResult, fallback: list[str] | None = None) -> None:
    missing = answer.missing_data or fallback or []
    if not missing:
        st.success("No requested fields are missing from the selected answer path.")
        return
    st.warning("Missing or intentionally abstained fields")
    for item in missing:
        st.write(f"- {item}")


def _contact_fact_rows(record: dict[str, Any]) -> tuple[list[tuple[str, str]], list[str]]:
    fields = [
        ("Primary email", "primary_email"),
        ("Primary phone", "primary_phone"),
        ("Principal LinkedIn", "principal_linkedin_url"),
        ("AUM", "aum_text"),
        ("SEC AUM", "sec_aum_usd"),
    ]
    rows: list[tuple[str, str]] = []
    missing: list[str] = []
    for label, field_name in fields:
        value = clean_text(record.get(field_name))
        if value:
            rows.append((label, value))
        else:
            missing.append(f"{label}: {NOT_EVIDENCED}.")
    return rows, missing


def _render_single_record_facts(
    result: RetrievalResult,
    answer: AnswerResult,
    record_id: str,
    record: dict[str, Any],
) -> None:
    hits = _record_hits(result, record_id)
    common_rows = [
        ("Family Office", _short_text(record.get("family_office_name"))),
        ("Record ID", record_id),
        ("Confidence", _record_confidence(record, hits, answer)),
        ("Source", _record_source(record, hits)),
    ]

    if result.intent.intent == "regulatory":
        rows = [
            ("SEC registered", "Yes" if to_bool(record.get("sec_registered")) else "No"),
            ("CRD", _field_or_missing(record, "sec_crd_number")),
            ("Registration status", _field_or_missing(record, "sec_registration_status")),
            ("SEC confidence", _field_or_missing(record, "sec_confidence")),
            *common_rows,
        ]
        _render_fact_pairs("Regulatory Facts", rows)
        _render_missing_fields(answer)
        return

    if result.intent.intent == "contact_lookup":
        rows, missing = _contact_fact_rows(record)
        _render_fact_pairs("Evidenced Contact Fields", rows or common_rows)
        _render_missing_fields(answer, missing)
        return

    if result.intent.intent == "recent_activity":
        rows = [
            ("Family Office", _short_text(record.get("family_office_name"))),
            ("Date", _field_or_missing(record, "recent_activity_date")),
            ("Outlet", _field_or_missing(record, "recent_activity_outlet")),
            ("Activity Type", _field_or_missing(record, "recent_activity_type")),
            ("Activity", _field_or_missing(record, "recent_activity")),
            ("Record ID", record_id),
            ("Source", _record_source(record, hits)),
        ]
        _render_fact_pairs("Recent Activity Facts", rows)
        _render_missing_fields(answer)
        return

    rows = [
        ("Family Office", _short_text(record.get("family_office_name"))),
        ("Type", _field_or_missing(record, "family_office_type")),
        ("Location", _location(record)),
        ("Record ID", record_id),
        ("Confidence", _record_confidence(record, hits, answer)),
        ("Source", _record_source(record, hits)),
    ]
    _render_fact_pairs("Entity Facts", rows)
    _render_missing_fields(answer)


def _listing_rows(record_ids: list[str], records: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for record_id in record_ids:
        record = records.get(record_id)
        if not record:
            continue
        rows.append(
            {
                "Record ID": record_id,
                "Family Office": _short_text(record.get("family_office_name")),
                "Type": _field_or_missing(record, "family_office_type"),
                "Location": _location(record),
                "SEC": "Registered" if to_bool(record.get("sec_registered")) else "Not shown registered",
                "CRD": _short_text(record.get("sec_crd_number")),
                "Source": _source_domain_text(_source_urls_from_record(record)),
            }
        )
    return rows


def _comparison_rows(record_ids: list[str], records: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    labels = [
        ("Type", "family_office_type"),
        ("Location", "location"),
        ("SEC status", "sec_status"),
        ("CRD", "sec_crd_number"),
        ("Primary email", "primary_email"),
        ("Primary phone", "primary_phone"),
        ("AUM", "aum_text"),
        ("SEC AUM", "sec_aum_usd"),
    ]
    selected_records = [(record_id, records[record_id]) for record_id in record_ids if record_id in records]
    rows: list[dict[str, str]] = []
    for label, field_name in labels:
        row = {"Field": label}
        for record_id, record in selected_records:
            name = _short_text(record.get("family_office_name"), record_id)
            if field_name == "location":
                value = _location(record)
            elif field_name == "sec_status":
                value = "SEC-registered" if to_bool(record.get("sec_registered")) else "Not shown SEC-registered"
            else:
                value = _field_or_missing(record, field_name)
            row[f"{name} ({record_id})"] = value
        rows.append(row)
    return rows


def _render_comparison_panels(record_ids: list[str], records: dict[str, dict[str, Any]]) -> None:
    selected_records = [(record_id, records[record_id]) for record_id in record_ids if record_id in records]
    if not selected_records:
        return

    columns = st.columns(min(2, len(selected_records)))
    for index, (record_id, record) in enumerate(selected_records):
        with columns[index % len(columns)]:
            rows = [
                ("Type", _field_or_missing(record, "family_office_type")),
                ("Location", _location(record)),
                (
                    "SEC status",
                    "SEC-registered" if to_bool(record.get("sec_registered")) else "Not shown SEC-registered",
                ),
                ("CRD", _field_or_missing(record, "sec_crd_number")),
                ("Primary email", _field_or_missing(record, "primary_email")),
                ("Primary phone", _field_or_missing(record, "primary_phone")),
                ("AUM", _field_or_missing(record, "aum_text")),
                ("SEC AUM", _field_or_missing(record, "sec_aum_usd")),
            ]
            title = f"{_short_text(record.get('family_office_name'), record_id)} ({record_id})"
            _render_fact_pairs(title, rows)


def _render_structured_facts(
    result: RetrievalResult,
    answer: AnswerResult,
    records: dict[str, dict[str, Any]],
) -> None:
    record_ids = _selected_record_ids(result, answer)

    if result.intent.intent == "filtered_listing":
        rows = _listing_rows(record_ids, records)
        st.markdown("**Filtered Records**")
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        return

    if result.intent.intent == "comparison":
        rows = _comparison_rows(record_ids[:4], records)
        st.markdown("**Side-by-Side Records**")
        _render_comparison_panels(record_ids[:4], records)
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        _render_missing_fields(answer)
        return

    if not record_ids:
        st.info("No selected record was available for structured fact display.")
        _render_missing_fields(answer)
        return

    record_id = record_ids[0]
    record = records.get(record_id)
    if not record:
        st.info("The selected record was not found in the locked dataset.")
        _render_missing_fields(answer)
        return
    _render_single_record_facts(result, answer, record_id, record)


def _citation_rows(answer: AnswerResult) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for citation in answer.citations:
        source_domain = _domain(citation.source_url)
        key = (citation.record_id, citation.chunk_type, citation.field_name, source_domain)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "Record": citation.record_id,
                "Family Office": citation.family_office_name,
                "Chunk": citation.chunk_type,
                "Field": citation.field_name or "-",
                "Source Domain": source_domain,
                "URL": citation.source_url,
            }
        )
    return rows


def _render_citations(answer: AnswerResult) -> None:
    rows = _citation_rows(answer)
    if not rows:
        st.info("No citations were emitted for this response.")
        return
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
        column_config={"URL": st.column_config.LinkColumn("URL")},
    )


def _badge_list(hit: RetrievalHit) -> list[str]:
    badges = [_why(hit)]
    if hit.chunk_type == "record_profile":
        badges.append("Record profile")
    if hit.chunk_type == "regulatory":
        badges.append("Regulatory")
    if hit.chunk_type == "recent_activity":
        badges.append("Recent activity")
    if hit.chunk_type == "contact_policy":
        badges.append("Sensitive-field policy")
    if clean_text(hit.metadata.get("validation_status")).lower() == "accepted":
        badges.append("Validated")
    if clean_text(hit.metadata.get("confidence_label")).lower() == "high":
        badges.append("High confidence")
    if clean_text(hit.metadata.get("safe_answer_policy")):
        badges.append("Evidence only")
    return list(dict.fromkeys(badges))


def _record_grouped_evidence_rows(hits: list[RetrievalHit]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for hit in hits:
        rows.append(
            {
                "Chunk": hit.chunk_type,
                "Badges": ", ".join(_badge_list(hit)),
                "Field": _short_text(hit.metadata.get("field_name")),
                "Value": _short_text(hit.metadata.get("field_value_text")),
                "Confidence": _short_text(hit.metadata.get("confidence_label")),
                "Sources": _source_domain_text(_source_urls(hit)),
            }
        )
    return rows


def _render_record_sources(hits: list[RetrievalHit]) -> None:
    urls: list[str] = []
    for hit in hits:
        urls.extend(_source_urls(hit))
    source_rows = _deduped_domain_links(list(dict.fromkeys(urls)))
    if not source_rows:
        st.write("Sources: -")
        return
    st.dataframe(
        pd.DataFrame(source_rows),
        hide_index=True,
        use_container_width=True,
        column_config={"URL": st.column_config.LinkColumn("URL")},
    )


def _render_record_evidence(record_id: str, hits: list[RetrievalHit], records: dict[str, dict[str, Any]]) -> None:
    record = records.get(record_id, {})
    name = _short_text(record.get("family_office_name") or hits[0].metadata.get("family_office_name"), record_id)
    st.markdown(f"**{name} ({record_id})**")
    st.caption(" | ".join(_badge_list(hits[0])))
    st.dataframe(
        pd.DataFrame(_record_grouped_evidence_rows(hits)),
        hide_index=True,
        use_container_width=True,
    )
    _render_record_sources(hits)
    uncertainty = clean_text(record.get("uncertainty_notes") or hits[0].metadata.get("uncertainty_notes"))
    if uncertainty:
        st.caption(f"Uncertainty: {uncertainty}")
    for hit in hits:
        label = f"Raw chunk: {hit.chunk_type} ({hit.chunk_id})"
        with st.expander(label, expanded=False):
            st.code(hit.text)


def _candidate_summary_rows(hits: list[RetrievalHit]) -> list[dict[str, str]]:
    grouped = _hits_by_record(hits)
    rows: list[dict[str, str]] = []
    for record_id, record_hits in grouped.items():
        first = record_hits[0]
        rows.append(
            {
                "Record": record_id,
                "Family Office": _short_text(first.metadata.get("family_office_name")),
                "Chunks": str(len(record_hits)),
                "Top Badges": ", ".join(_badge_list(first)),
                "Sources": _source_domain_text(_source_urls(first)),
            }
        )
    return rows


def _render_evidence_review(
    result: RetrievalResult,
    answer: AnswerResult,
    records: dict[str, dict[str, Any]],
) -> None:
    selected_ids = _selected_record_ids(result, answer)
    selected_id_set = set(selected_ids)
    grouped = _hits_by_record(result.hits)
    selected_hits = [hit for hit in result.hits if hit.record_id in selected_id_set]
    other_hits = [hit for hit in result.hits if hit.record_id not in selected_id_set]

    st.subheader("Evidence Review")
    meta1, meta2, meta3 = st.columns(3)
    meta1.metric("Intent", result.intent.intent)
    meta2.metric("Records Retrieved", len(grouped))
    meta3.metric("Chunks Retrieved", len(result.hits))

    if result.intent.filters:
        st.caption(f"Parsed filters: {result.intent.filters}")

    st.markdown("**Selected Evidence**")
    if not selected_hits:
        st.info("No selected evidence was available.")
    else:
        for index, record_id in enumerate(selected_ids):
            hits = grouped.get(record_id, [])
            if not hits:
                continue
            record = records.get(record_id, {})
            name = _short_text(record.get("family_office_name") or hits[0].metadata.get("family_office_name"), record_id)
            with st.expander(f"{name} ({record_id})", expanded=index == 0):
                _render_record_evidence(record_id, hits, records)

    with st.expander(f"Other Retrieved Candidates ({len({hit.record_id for hit in other_hits})})", expanded=False):
        if not other_hits:
            st.write("No unrelated candidates retrieved.")
            return
        st.dataframe(
            pd.DataFrame(_candidate_summary_rows(other_hits)),
            hide_index=True,
            use_container_width=True,
        )
        for record_id, hits in _hits_by_record(other_hits).items():
            record = records.get(record_id, {})
            name = _short_text(record.get("family_office_name") or hits[0].metadata.get("family_office_name"), record_id)
            with st.expander(f"{name} ({record_id})", expanded=False):
                _render_record_evidence(record_id, hits, records)


def _reasoning_steps(result: RetrievalResult, answer: AnswerResult) -> list[str]:
    selected_hits = [
        hit
        for hit in result.hits
        if hit.record_id in set(_selected_record_ids(result, answer))
    ]
    steps = [f"Intent classified as `{result.intent.intent}`."]
    if result.intent.intent == "filtered_listing":
        record_ids = list(dict.fromkeys(hit.record_id for hit in selected_hits))
        steps.append(f"Records selected by parsed filters: `{', '.join(record_ids)}`.")
    elif result.intent.matched_record_ids:
        steps.append(f"Exact record match found: `{', '.join(result.intent.matched_record_ids)}`.")
    elif selected_hits:
        steps.append(f"Selected record came from retrieval: `{selected_hits[0].record_id}`.")
    else:
        steps.append("No selected record was available.")

    if selected_hits:
        chunk_types = list(dict.fromkeys(hit.chunk_type for hit in selected_hits))
        steps.append(f"Supporting chunk: `{', '.join(chunk_types[:3])}`.")

    if answer.abstain:
        steps.append("Answer abstained because requested evidence was missing or unsafe to infer.")
    else:
        steps.append("Answer allowed because requested fields are present in selected evidence.")

    if result.intent.requested_fields:
        steps.append(f"Requested fields: `{', '.join(result.intent.requested_fields)}`.")
    sensitive_fields = {
        "primary_email",
        "primary_phone",
        "principal_linkedin_url",
        "aum_text",
        "sec_registered",
        "sec_crd_number",
        "recent_activity",
    }
    if sensitive_fields & set(result.intent.requested_fields):
        steps.append("Sensitive fields were not inferred.")
    return steps


def _render_reasoning_path(result: RetrievalResult, answer: AnswerResult) -> None:
    for step in _reasoning_steps(result, answer):
        st.write(f"- {step}")


def _render_answer_status(answer: AnswerResult) -> None:
    label = "Abstained: requested evidence missing" if answer.abstain else "Answered from selected evidence"
    with st.status(label, expanded=True, state="complete"):
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Status", "Abstained" if answer.abstain else "Answered")
        col2.metric("Confidence", answer.confidence.upper())
        col3.metric("Unsupported Claims", str(answer.unsupported_claim_count))
        col4.metric("Citations", str(len(answer.citations)))


def _render_answer_review(result: RetrievalResult, answer: AnswerResult) -> None:
    records = _records_by_id()

    st.subheader("Answer Review")
    _render_answer_status(answer)
    st.markdown("**Deterministic Answer**")
    st.write(answer.answer)
    _render_structured_facts(result, answer, records)

    tabs = st.tabs(["Reasoning Path", "Citations", "Missing Data", "Caveats"])
    with tabs[0]:
        _render_reasoning_path(result, answer)
    with tabs[1]:
        _render_citations(answer)
    with tabs[2]:
        _render_missing_fields(answer)
    with tabs[3]:
        if not answer.caveats:
            st.write("-")
        for caveat in answer.caveats:
            st.write(f"- {caveat}")

    _render_evidence_review(result, answer, records)


def _run_query(query: str, mode: str, top_k: int, use_reranker: bool) -> None:
    normalized_query = query.strip()
    with st.status("Running local retrieval and answer extraction", expanded=False) as status:
        result = retrieve(normalized_query, top_k=top_k, use_reranker=use_reranker)
        deterministic = answer_from_retrieval(result)
        answer = (
            rewrite_with_local_llm(normalized_query, deterministic, result.hits)
            if mode == "local_llm"
            else deterministic
        )
        status.update(label="Evidence review ready", state="complete", expanded=False)

    _render_answer_review(result, answer)


manifest = _load_manifest()

st.title("PolarityIQ Evidence Review Console")
st.caption("Local-only assessment UI for answer sufficiency, missing data, citations, and selected evidence.")

if not manifest:
    st.error("Build manifest not found. Run `python scripts/build_all.py` first.")
    st.stop()

_render_manifest_summary(manifest)

review_col, control_col = st.columns([3, 1], gap="large")
with control_col:
    query, mode, top_k, use_reranker, run = _render_control_panel(manifest)

with review_col:
    if run and query.strip():
        _run_query(query, mode, top_k, use_reranker)
    else:
        st.info("Ready for evidence review.")
