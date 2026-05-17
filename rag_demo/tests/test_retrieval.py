from __future__ import annotations

from src.answering.deterministic import answer_from_retrieval
from src.chunking.build_chunks import build_chunks_file
from src.config import CHUNKS_PATH, RAW_DATA_PATH
from src.indexing.build_bm25 import BM25_INDEX_PATH, build_bm25_index
from src.loaders.family_offices import load_family_offices
from src.retrieval.hybrid import retrieve
from src.retrieval.intent import (
    classify_intent,
    metadata_matches_filters,
    parse_filters,
    record_matches_filters,
)


def _ensure_lexical_index() -> None:
    rows = load_family_offices(RAW_DATA_PATH)
    chunks = build_chunks_file(rows, CHUNKS_PATH)
    build_bm25_index(chunks, BM25_INDEX_PATH)


def _top_record_ids(query: str, top_k: int = 5) -> list[str]:
    _ensure_lexical_index()
    result = retrieve(query, top_k=top_k)
    return list(dict.fromkeys(hit.record_id for hit in result.hits))


def test_retrieves_anchor_records_by_name_and_crd() -> None:
    assert _top_record_ids("Cat Trail Capital email", 3)[0] == "fo_001"
    assert "fo_002" in _top_record_ids("Ralph Family Office contact information", 3)
    assert _top_record_ids("Ohana Advisors CRD 158515", 3)[0] == "fo_003"
    assert _top_record_ids("Pathstone recent activity CRD 151736", 3)[0] == "fo_032"


def test_filtered_listing_uses_metadata_filters() -> None:
    _ensure_lexical_index()
    result = retrieve("Which SEC-registered family offices in California are in the dataset?", top_k=10)
    record_ids = {hit.record_id for hit in result.hits}
    assert {"fo_003", "fo_011", "fo_024", "fo_041"} & record_ids
    assert result.intent.intent == "filtered_listing"
    assert result.intent.filters["sec_registered"] is True


def test_answer_paths_cover_entity_regulatory_recent_listing_and_comparison() -> None:
    _ensure_lexical_index()

    entity = answer_from_retrieval(
        retrieve("What type of family office is Cat Trail Capital and where is it based?", top_k=8)
    )
    assert entity.abstain is False
    assert "Cat Trail Capital" in entity.answer

    regulatory_false = answer_from_retrieval(retrieve("Is Cat Trail Capital SEC registered?", top_k=8))
    assert regulatory_false.abstain is False
    assert "not shown as SEC-registered" in regulatory_false.answer

    regulatory_true = answer_from_retrieval(retrieve("Is Ohana Advisors SEC registered?", top_k=8))
    assert regulatory_true.abstain is False
    assert "CRD 158515" in regulatory_true.answer

    recent = answer_from_retrieval(retrieve("What recent activity is recorded for Pathstone?", top_k=8))
    assert recent.abstain is False
    assert "Pathstone" in recent.answer

    listing = answer_from_retrieval(
        retrieve("Which SEC-registered family offices in California are in the dataset?", top_k=10)
    )
    assert listing.abstain is False
    assert "Ohana Advisors" in listing.answer

    comparison = answer_from_retrieval(
        retrieve(
            "Compare Cat Trail Capital and Ohana Advisors on type, geography, SEC status, and contact availability.",
            top_k=10,
        )
    )
    assert comparison.abstain is False
    assert "Cat Trail Capital" in comparison.answer
    assert "Ohana Advisors" in comparison.answer


def test_intent_and_filter_helpers() -> None:
    rows = load_family_offices(RAW_DATA_PATH)
    cat = next(row for row in rows if row["record_id"] == "fo_001")
    ohana = next(row for row in rows if row["record_id"] == "fo_003")

    filters = parse_filters("List SEC-registered multi-family offices in California")
    assert filters["sec_registered"] is True
    assert filters["family_office_type"] == "multi_family_office"
    assert filters["state_region"] == "CA"

    assert record_matches_filters(ohana, filters) is True
    assert record_matches_filters(cat, filters) is False
    assert metadata_matches_filters(
        {
            "sec_registered": True,
            "family_office_type": "multi_family_office",
            "state_region": "",
            "city": "California",
        },
        filters,
    )
    intent = classify_intent("Which record has CRD 151736?", rows)
    assert intent.matched_record_ids == ["fo_032"]
