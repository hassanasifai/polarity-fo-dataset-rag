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

    for row in rows:
        result = retrieve(row["question"], top_k=12, dense_top_k=0)
        answer = answer_from_retrieval(result)
        ranked_record_ids = [hit.record_id for hit in result.hits]
        unique_records = _unique_record_ids(ranked_record_ids)
        hit_at_3, reciprocal_rank, recall_at_5 = _record_scores(
            ranked_record_ids,
            row.get("gold_record_ids", []),
            answer_abstained=answer.abstain,
        )

        expected_abstain = row.get("expected_behavior") == "abstain"
        body = _body_text(answer)
        required = row.get("must_include", [])
        forbidden = row.get("must_exclude", [])
        text_ok = _contains_all(body, required) and _excludes_all(body, forbidden)
        expected_intent = row.get("expected_intent")
        intent_ok = result.intent.intent == expected_intent if expected_intent else True
        retrieved_chunk_ids = {hit.chunk_id for hit in result.hits}

        metric_lists["hit_at_3"].append(hit_at_3)
        metric_lists["mrr"].append(reciprocal_rank)
        metric_lists["record_recall_at_5"].append(recall_at_5)
        metric_lists["citation_accuracy"].append(_citation_score(answer, retrieved_chunk_ids))
        metric_lists["abstention_accuracy"].append(1.0 if answer.abstain == expected_abstain else 0.0)
        metric_lists["missing_data_honesty"].append(_missing_honesty_score(expected_abstain, body))
        metric_lists["answer_text_accuracy"].append(1.0 if text_ok else 0.0)
        metric_lists["intent_accuracy"].append(1.0 if intent_ok else 0.0)
        unsupported_claim_count += answer.unsupported_claim_count

        details.append(
            {
                "id": row["id"],
                "category": row["category"],
                "question": row["question"],
                "intent": result.intent.intent,
                "expected_intent": expected_intent or "-",
                "top_records": unique_records[:5],
                "answer_abstain": answer.abstain,
                "expected_behavior": row.get("expected_behavior", "answer"),
                "hit_at_3": hit_at_3,
                "mrr": reciprocal_rank,
                "record_recall_at_5": recall_at_5,
                "citation_accuracy": metric_lists["citation_accuracy"][-1],
                "abstention_accuracy": metric_lists["abstention_accuracy"][-1],
                "missing_data_honesty": metric_lists["missing_data_honesty"][-1],
                "answer_text_accuracy": metric_lists["answer_text_accuracy"][-1],
                "intent_accuracy": metric_lists["intent_accuracy"][-1],
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
        "The eval runner disables dense retrieval (`dense_top_k=0`) so the audit is fast, deterministic, and not",
        "dependent on local transformer model cache state; the Streamlit app still exposes the full hybrid path.",
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
            "| ID | Category | Intent | Expected | Top Records | Hit@3 | MRR | Recall@5 | Abstain OK | Citation OK | Text OK | Intent OK |",
            "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in metrics["details"]:
        lines.append(
            "| {id} | {category} | {intent} | {expected_behavior} | {top_records} | {hit_at_3:.0f} | "
            "{mrr:.3f} | {record_recall_at_5:.3f} | {abstention_accuracy:.0f} | "
            "{citation_accuracy:.0f} | {answer_text_accuracy:.0f} | {intent_accuracy:.0f} |".format(**row)
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
            f"Observed intent `{row['intent']}`, top records `{row['top_records']}`. {notes}"
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
            "What this eval does not measure: live web freshness, SMTP deliverability, Form ADV PDF parsing,",
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
