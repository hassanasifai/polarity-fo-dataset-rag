from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from src.answering.deterministic import answer_from_retrieval
from src.config import GOLDEN_EVAL_PATH, REPORTS_DIR
from src.eval.golden_set import GOLDEN_QUESTIONS
from src.retrieval.hybrid import retrieve

ENTITY_RESOLUTION_INTENTS = {
    "entity_lookup",
    "contact_lookup",
    "regulatory",
    "recent_activity",
    "comparison",
}
RETRIEVAL_METRIC_KEYS = ["hit_at_3", "mrr", "record_recall_at_5"]


def write_golden_eval(path: Path = GOLDEN_EVAL_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for question in GOLDEN_QUESTIONS:
            file.write(json.dumps(question) + "\n")
    return path


def load_golden_eval(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        write_golden_eval(path)
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _first_relevant_rank(record_ids: list[str], gold_record_ids: list[str]) -> int | None:
    if not gold_record_ids:
        return None
    for rank, record_id in enumerate(record_ids, start=1):
        if record_id in gold_record_ids:
            return rank
    return None


def _unique_record_ids(record_ids: list[str]) -> list[str]:
    return list(dict.fromkeys(record_ids))


def _mean(values: list[float]) -> float:
    return mean(values) if values else 0.0


def _body_text(answer: Any) -> str:
    return " ".join([answer.answer, *answer.missing_data, *answer.caveats]).lower()


def _contains_all(text: str, required: list[str]) -> bool:
    return all(item.lower() in text for item in required)


def _excludes_all(text: str, forbidden: list[str]) -> bool:
    return all(item.lower() not in text for item in forbidden)


def _missing_honesty_score(expected_abstain: bool, body: str) -> float:
    if not expected_abstain:
        return 1.0
    honest_markers = [
        "not evidenced",
        "no matching",
        "no evidence",
        "not in the locked dataset",
    ]
    return 1.0 if any(marker in body for marker in honest_markers) else 0.0


def _record_scores(
    ranked_record_ids: list[str],
    gold_record_ids: list[str],
    *,
    answer_abstained: bool,
) -> tuple[float, float, float]:
    if not gold_record_ids:
        negative_score = 1.0 if answer_abstained else 0.0
        return negative_score, negative_score, negative_score

    unique_records = _unique_record_ids(ranked_record_ids)
    first_rank = _first_relevant_rank(ranked_record_ids, gold_record_ids)
    gold = set(gold_record_ids)
    retrieved = set(unique_records[:5])
    return (
        1.0 if first_rank is not None and first_rank <= 3 else 0.0,
        1.0 / first_rank if first_rank else 0.0,
        len(gold & retrieved) / len(gold),
    )


def _citation_score(answer: Any, retrieved_chunk_ids: set[str]) -> float:
    if answer.abstain:
        return 1.0
    return (
        1.0
        if answer.citations and all(citation.chunk_id in retrieved_chunk_ids for citation in answer.citations)
        else 0.0
    )


def _entity_resolution_score(row: dict[str, Any], result: Any) -> float | None:
    expected_intent = row.get("expected_intent")
    if expected_intent not in ENTITY_RESOLUTION_INTENTS:
        return None

    gold_record_ids = row.get("gold_record_ids", [])
    matched_record_ids = result.intent.matched_record_ids
    if not gold_record_ids:
        return 1.0 if not matched_record_ids else 0.0
    return 1.0 if set(gold_record_ids) & set(matched_record_ids) else 0.0


def _structured_filter_score(row: dict[str, Any], result: Any, *, answer_abstained: bool) -> float | None:
    if row.get("expected_intent") != "filtered_listing":
        return None

    expected_abstain = row.get("expected_behavior") == "abstain"
    if expected_abstain:
        return 1.0 if answer_abstained else 0.0
    if answer_abstained or result.intent.intent != "filtered_listing":
        return 0.0

    gold_record_ids = row.get("gold_record_ids", [])
    if not gold_record_ids:
        return 1.0
    top_records = set(_unique_record_ids([hit.record_id for hit in result.hits])[:5])
    return 1.0 if top_records & set(gold_record_ids) else 0.0


def _negative_control_score(row: dict[str, Any], *, answer_abstained: bool, text_ok: bool) -> float | None:
    is_negative = row.get("expected_behavior") == "abstain" and not row.get("gold_record_ids", [])
    if not is_negative:
        return None
    return 1.0 if answer_abstained and text_ok else 0.0


def evaluate_questions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    unsupported_claim_count = 0

    metric_lists: dict[str, list[float]] = {
        "hit_at_3": [],
        "mrr": [],
        "record_recall_at_5": [],
        "citation_accuracy": [],
        "abstention_accuracy": [],
        "missing_data_honesty": [],
        "answer_text_accuracy": [],
        "intent_accuracy": [],
    }
    bm25_metric_lists: dict[str, list[float]] = {key: [] for key in RETRIEVAL_METRIC_KEYS}
    entity_resolution_scores: list[float] = []
    structured_filter_scores: list[float] = []
    negative_control_scores: list[float] = []

    for row in rows:
        ui_result = retrieve(row["question"], top_k=12)
        answer = answer_from_retrieval(ui_result)
        metric_result = retrieve(
            row["question"],
            top_k=12,
            include_exact_seeds=False,
            include_filter_seeds=False,
        )
        bm25_result = retrieve(
            row["question"],
            top_k=12,
            dense_top_k=0,
            include_exact_seeds=False,
            include_filter_seeds=False,
        )

        ranked_record_ids = [hit.record_id for hit in metric_result.hits]
        unique_records = _unique_record_ids(ranked_record_ids)
        ui_records = _unique_record_ids([hit.record_id for hit in ui_result.hits])
        bm25_records = _unique_record_ids([hit.record_id for hit in bm25_result.hits])
        hit_at_3, reciprocal_rank, recall_at_5 = _record_scores(
            ranked_record_ids,
            row.get("gold_record_ids", []),
            answer_abstained=answer.abstain,
        )
        bm25_hit_at_3, bm25_reciprocal_rank, bm25_recall_at_5 = _record_scores(
            [hit.record_id for hit in bm25_result.hits],
            row.get("gold_record_ids", []),
            answer_abstained=answer.abstain,
        )

        expected_abstain = row.get("expected_behavior") == "abstain"
        body = _body_text(answer)
        required = row.get("must_include", [])
        forbidden = row.get("must_exclude", [])
        text_ok = _contains_all(body, required) and _excludes_all(body, forbidden)
        expected_intent = row.get("expected_intent")
        intent_ok = ui_result.intent.intent == expected_intent if expected_intent else True
        retrieved_chunk_ids = {hit.chunk_id for hit in ui_result.hits}
        entity_score = _entity_resolution_score(row, ui_result)
        structured_score = _structured_filter_score(row, ui_result, answer_abstained=answer.abstain)
        negative_score = _negative_control_score(row, answer_abstained=answer.abstain, text_ok=text_ok)

        metric_lists["hit_at_3"].append(hit_at_3)
        metric_lists["mrr"].append(reciprocal_rank)
        metric_lists["record_recall_at_5"].append(recall_at_5)
        bm25_metric_lists["hit_at_3"].append(bm25_hit_at_3)
        bm25_metric_lists["mrr"].append(bm25_reciprocal_rank)
        bm25_metric_lists["record_recall_at_5"].append(bm25_recall_at_5)
        metric_lists["citation_accuracy"].append(_citation_score(answer, retrieved_chunk_ids))
        metric_lists["abstention_accuracy"].append(1.0 if answer.abstain == expected_abstain else 0.0)
        metric_lists["missing_data_honesty"].append(_missing_honesty_score(expected_abstain, body))
        metric_lists["answer_text_accuracy"].append(1.0 if text_ok else 0.0)
        metric_lists["intent_accuracy"].append(1.0 if intent_ok else 0.0)
        if entity_score is not None:
            entity_resolution_scores.append(entity_score)
        if structured_score is not None:
            structured_filter_scores.append(structured_score)
        if negative_score is not None:
            negative_control_scores.append(negative_score)
        unsupported_claim_count += answer.unsupported_claim_count

        details.append(
            {
                "id": row["id"],
                "category": row["category"],
                "question": row["question"],
                "intent": ui_result.intent.intent,
                "expected_intent": expected_intent or "-",
                "top_records": ui_records[:5],
                "retrieval_top_records": unique_records[:5],
                "bm25_top_records": bm25_records[:5],
                "answer_abstain": answer.abstain,
                "expected_behavior": row.get("expected_behavior", "answer"),
                "hit_at_3": hit_at_3,
                "mrr": reciprocal_rank,
                "record_recall_at_5": recall_at_5,
                "bm25_hit_at_3": bm25_hit_at_3,
                "bm25_mrr": bm25_reciprocal_rank,
                "bm25_record_recall_at_5": bm25_recall_at_5,
                "citation_accuracy": metric_lists["citation_accuracy"][-1],
                "abstention_accuracy": metric_lists["abstention_accuracy"][-1],
                "missing_data_honesty": metric_lists["missing_data_honesty"][-1],
                "answer_text_accuracy": metric_lists["answer_text_accuracy"][-1],
                "intent_accuracy": metric_lists["intent_accuracy"][-1],
                "entity_resolution_accuracy": entity_score,
                "structured_filter_accuracy": structured_score,
                "negative_control_accuracy": negative_score,
                "failure_mode": row.get("failure_mode", ""),
                "notes": row.get("notes", ""),
                "answer_excerpt": answer.answer[:180].replace("\n", " "),
            }
        )

    metrics: dict[str, Any] = {
        "question_count": len(rows),
        "unsupported_claim_count": unsupported_claim_count,
        "details": details,
    }
    for key, values in metric_lists.items():
        metrics[key] = _mean(values)
    metrics["bm25_fallback"] = {key: _mean(values) for key, values in bm25_metric_lists.items()}
    metrics["entity_resolution_accuracy"] = _mean(entity_resolution_scores)
    metrics["structured_filter_accuracy"] = _mean(structured_filter_scores)
    metrics["negative_control_accuracy"] = _mean(negative_control_scores)
    metrics["category_summary"] = _category_summary(details)
    return metrics


def _category_summary(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in details:
        grouped[row["category"]].append(row)

    summary: list[dict[str, Any]] = []
    for category, rows in sorted(grouped.items()):
        summary.append(
            {
                "category": category,
                "questions": len(rows),
                "hit_at_3": _mean([row["hit_at_3"] for row in rows]),
                "recall_at_5": _mean([row["record_recall_at_5"] for row in rows]),
                "answer_text_accuracy": _mean([row["answer_text_accuracy"] for row in rows]),
                "abstention_accuracy": _mean([row["abstention_accuracy"] for row in rows]),
                "intent_accuracy": _mean([row["intent_accuracy"] for row in rows]),
            }
        )
    return summary


def _known_limits(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in details if row.get("failure_mode") or row["answer_text_accuracy"] < 1.0]


def _markdown_report(metrics: dict[str, Any]) -> str:
    lines = [
        "# PolarityIQ Stage 1 Local RAG Evaluation Report",
        "",
        "This report is generated by `python -m src.eval.run_eval` against the locked local dataset and local indexes.",
        "Answer quality is evaluated on the same default hybrid retrieval path used by the Streamlit app.",
        "Retrieval Hit@3/MRR/Recall@5 are computed on a hybrid retrieval-only pass with exact entity and metadata",
        "seeds disabled, so entity resolution and structured filter assistance are reported separately.",
        "The golden set is intentionally not a showcase script: it includes canonical queries, negative controls,",
        "sensitive-field probes, entity aliases, broad filters, multi-hop questions, and typo/adversarial wording.",
        "",
        "## Summary Metrics",
        "",
        f"- Questions: {metrics['question_count']}",
        f"- hit_at_3: {metrics['hit_at_3']:.3f}",
        f"- MRR: {metrics['mrr']:.3f}",
        f"- record_recall_at_5: {metrics['record_recall_at_5']:.3f}",
        f"- citation_accuracy: {metrics['citation_accuracy']:.3f}",
        f"- unsupported_claim_count: {metrics['unsupported_claim_count']}",
        f"- abstention_accuracy: {metrics['abstention_accuracy']:.3f}",
        f"- missing_data_honesty: {metrics['missing_data_honesty']:.3f}",
        f"- answer_text_accuracy: {metrics['answer_text_accuracy']:.3f}",
        f"- intent_accuracy: {metrics['intent_accuracy']:.3f}",
        f"- entity_resolution_accuracy: {metrics['entity_resolution_accuracy']:.3f}",
        f"- structured_filter_accuracy: {metrics['structured_filter_accuracy']:.3f}",
        f"- negative_control_accuracy: {metrics['negative_control_accuracy']:.3f}",
        "",
        "## BM25-Only Fallback Metrics",
        "",
        "These metrics use `dense_top_k=0` and the same seed-disabled retrieval metric pass.",
        "",
        f"- bm25_hit_at_3: {metrics['bm25_fallback']['hit_at_3']:.3f}",
        f"- bm25_MRR: {metrics['bm25_fallback']['mrr']:.3f}",
        f"- bm25_record_recall_at_5: {metrics['bm25_fallback']['record_recall_at_5']:.3f}",
        "",
        "## Per-Category Metrics",
        "",
        "| Category | Questions | Hit@3 | Recall@5 | Answer Text | Abstain OK | Intent OK |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in metrics["category_summary"]:
        lines.append(
            "| {category} | {questions} | {hit_at_3:.3f} | {recall_at_5:.3f} | "
            "{answer_text_accuracy:.3f} | {abstention_accuracy:.3f} | {intent_accuracy:.3f} |".format(**row)
        )

    lines.extend(
        [
            "",
            "## Question Details",
            "",
            "| ID | Category | Intent | Expected | UI Top Records | Metric Top Records | BM25 Top Records | Hit@3 | MRR | Recall@5 | BM25 Hit@3 | Abstain OK | Citation OK | Text OK | Intent OK |",
            "|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in metrics["details"]:
        lines.append(
            "| {id} | {category} | {intent} | {expected_behavior} | {top_records} | "
            "{retrieval_top_records} | {bm25_top_records} | {hit_at_3:.0f} | "
            "{mrr:.3f} | {record_recall_at_5:.3f} | {bm25_hit_at_3:.0f} | "
            "{abstention_accuracy:.0f} | {citation_accuracy:.0f} | {answer_text_accuracy:.0f} | "
            "{intent_accuracy:.0f} |".format(**row)
        )

    known_limits = _known_limits(metrics["details"])
    lines.extend(
        [
            "",
            "## Known Limits Surfaced By This Eval",
            "",
        ]
    )
    if not known_limits:
        lines.append("No known limits were surfaced by this run, which should be treated as a warning sign and expanded.")
    for row in known_limits:
        failure = row.get("failure_mode") or "metric_miss"
        notes = row.get("notes") or "No extra notes."
        lines.append(
            f"- `{row['id']}` ({row['category']}): {failure}. "
            f"Observed intent `{row['intent']}`, UI top records `{row['top_records']}`, "
            f"metric top records `{row['retrieval_top_records']}`. {notes}"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This evaluation is deliberately adversarial enough to show dents. Canonical entity, regulatory,",
            "contact-missingness, and citation paths are expected to remain strong. The weaker areas are the ones",
            "a human evaluator should know about before trusting the demo: undocumented aliases, city-level filters,",
            "compound missingness filters, typo recovery, and true aggregate reasoning.",
            "",
            "What this eval does not measure: live web freshness, SMTP deliverability, Form ADV Schedule A officer parsing,",
            "principal-level personal contact discovery, or legal correctness of SEC status beyond the locked",
            "validation snapshot. The intended behavior for those gaps is abstention or explicit caveat, not inference.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_eval_to_report(
    eval_path: Path = GOLDEN_EVAL_PATH,
    out_path: Path = REPORTS_DIR / "eval_report.md",
) -> dict[str, Any]:
    rows = load_golden_eval(eval_path)
    metrics = evaluate_questions(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_markdown_report(metrics), encoding="utf-8")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local deterministic RAG evaluation.")
    parser.add_argument("--eval", type=Path, default=GOLDEN_EVAL_PATH)
    parser.add_argument("--out", type=Path, default=REPORTS_DIR / "eval_report.md")
    args = parser.parse_args()
    metrics = run_eval_to_report(args.eval, args.out)
    print(json.dumps({key: value for key, value in metrics.items() if key != "details"}, indent=2))
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
