from __future__ import annotations

from src.eval import run_eval
from src.schema import AnswerResult, IntentAnalysis, RetrievalHit, RetrievalResult


def _hit(record_id: str, *, why_retrieved: str) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=f"{record_id}::record_profile",
        record_id=record_id,
        chunk_type="record_profile",
        text=f"Record profile for {record_id}.",
        metadata={"family_office_name": "Cat Trail Capital", "source_urls": ["https://example.com"]},
        why_retrieved=why_retrieved,
    )


def _result(record_id: str, *, why_retrieved: str) -> RetrievalResult:
    return RetrievalResult(
        query="What type of family office is Cat Trail Capital?",
        intent=IntentAnalysis(
            intent="entity_lookup",
            matched_record_ids=["fo_001"],
            matched_record_names=["Cat Trail Capital"],
            preferred_chunk_types=["record_profile"],
            needs_exact_entity=True,
        ),
        hits=[_hit(record_id, why_retrieved=why_retrieved)],
    )


def test_eval_reports_hybrid_metrics_and_bm25_fallback_separately(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_retrieve(query: str, **kwargs: object) -> RetrievalResult:
        calls.append(kwargs)
        if kwargs.get("dense_top_k") == 0:
            return _result("fo_999", why_retrieved="bm25")
        if kwargs.get("include_exact_seeds") is False:
            return _result("fo_001", why_retrieved="dense+bm25")
        return _result("fo_001", why_retrieved="exact_record_match")

    def fake_answer_from_retrieval(result: RetrievalResult) -> AnswerResult:
        return AnswerResult(answer="Cat Trail Capital", confidence="high", abstain=False)

    monkeypatch.setattr(run_eval, "retrieve", fake_retrieve)
    monkeypatch.setattr(run_eval, "answer_from_retrieval", fake_answer_from_retrieval)

    metrics = run_eval.evaluate_questions(
        [
            {
                "id": "q001",
                "category": "entity_lookup_canonical",
                "question": "What type of family office is Cat Trail Capital?",
                "gold_record_ids": ["fo_001"],
                "expected_behavior": "answer",
                "must_include": ["Cat Trail Capital"],
                "expected_intent": "entity_lookup",
            }
        ]
    )

    assert calls[0] == {"top_k": 12}
    assert calls[1] == {"top_k": 12, "include_exact_seeds": False, "include_filter_seeds": False}
    assert calls[2] == {
        "top_k": 12,
        "dense_top_k": 0,
        "include_exact_seeds": False,
        "include_filter_seeds": False,
    }
    assert metrics["hit_at_3"] == 1.0
    assert metrics["bm25_fallback"]["hit_at_3"] == 0.0
    assert metrics["entity_resolution_accuracy"] == 1.0
