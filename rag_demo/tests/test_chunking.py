from __future__ import annotations

from collections import Counter

from src.chunking.build_chunks import build_chunks, metadata_key_coverage
from src.config import RAW_DATA_PATH
from src.loaders.family_offices import (
    clean_text,
    load_family_offices,
    parse_source_urls,
    to_bool,
    to_int,
)


def test_dataset_contract_matches_locked_shape() -> None:
    rows = load_family_offices(RAW_DATA_PATH)
    assert len(rows) == 50
    assert len(rows[0]) == 137

    by_id = {row["record_id"]: row for row in rows}
    assert by_id["fo_001"]["family_office_name"] == "Cat Trail Capital"
    assert by_id["fo_001"]["primary_email"] == "admin@cattrail.com"
    assert by_id["fo_001"]["primary_phone"] == ""
    assert by_id["fo_001"]["aum_text"] == ""
    assert to_bool(by_id["fo_001"]["sec_registered"]) is False
    assert by_id["fo_001"]["principal_1_name"] == "David Dekker"
    assert by_id["fo_001"]["primary_email_smtp_verified"] is False

    assert by_id["fo_002"]["primary_email"] == ""
    assert by_id["fo_002"]["primary_phone"] == ""
    assert by_id["fo_002"]["aum_text"] == ""
    assert to_bool(by_id["fo_002"]["sec_registered"]) is False

    assert by_id["fo_003"]["primary_email"] == "investments@ohanaadvisors.com"
    assert by_id["fo_003"]["primary_phone"] == "415-226-4170"
    assert to_bool(by_id["fo_003"]["sec_registered"]) is True
    assert by_id["fo_003"]["sec_crd_number"] == "158515"
    assert by_id["fo_003"]["sec_aum_usd"] != ""

    assert to_bool(by_id["fo_032"]["sec_registered"]) is True
    assert by_id["fo_032"]["sec_crd_number"] == "151736"
    assert by_id["fo_032"]["recent_activity"] != ""


def test_chunk_counts_and_required_metadata() -> None:
    rows = load_family_offices(RAW_DATA_PATH)
    chunks = build_chunks(rows)
    counts = Counter(chunk.metadata.chunk_type for chunk in chunks)

    assert counts["record_profile"] == 50
    assert counts["contact_policy"] == 50
    assert counts["regulatory"] == 50
    assert counts["recent_activity"] == 21
    assert counts["field_evidence"] >= 150

    coverage = metadata_key_coverage(chunks)
    assert all(coverage.values()), [key for key, covered in coverage.items() if not covered]
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)


def test_contact_policy_preserves_missing_sensitive_fields() -> None:
    rows = load_family_offices(RAW_DATA_PATH)
    chunks = build_chunks(rows)
    by_chunk_id = {chunk.chunk_id: chunk for chunk in chunks}

    cat_policy = by_chunk_id["fo_001::contact_policy"]
    ralph_policy = by_chunk_id["fo_002::contact_policy"]

    assert "Primary email: admin@cattrail.com" in cat_policy.text
    assert "Primary phone: not evidenced in the locked dataset" in cat_policy.text
    assert "AUM: not evidenced in the locked dataset" in cat_policy.text
    assert "Primary email: not evidenced in the locked dataset" in ralph_policy.text
    assert "Primary phone: not evidenced in the locked dataset" in ralph_policy.text
    assert "AUM: not evidenced in the locked dataset" in ralph_policy.text


def test_loader_normalizers_handle_dataset_edge_cases() -> None:
    assert clean_text(None) == ""
    assert clean_text(True) == "true"
    assert to_bool("YES") is True
    assert to_bool("False") is False
    assert to_int("42.0") == 42
    assert to_int("not a number") == 0
    assert parse_source_urls("['https://a.example', 'https://b.example']") == [
        "https://a.example",
        "https://b.example",
    ]
    assert parse_source_urls("https://a.example|https://b.example") == [
        "https://a.example",
        "https://b.example",
    ]
