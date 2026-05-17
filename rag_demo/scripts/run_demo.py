from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.answering.deterministic import answer_from_retrieval, ask
from src.answering.local_llm import rewrite_with_local_llm
from src.config import DEMO_QUERIES
from src.retrieval.hybrid import retrieve


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local PolarityIQ RAG demo queries.")
    parser.add_argument("query", nargs="?", help="Question to ask. If omitted, built-in demos run.")
    parser.add_argument("--mode", choices=["safe_extract", "local_llm"], default="safe_extract")
    parser.add_argument("--rerank", action="store_true", help="Use optional local cross-encoder reranker.")
    args = parser.parse_args()

    queries = [args.query] if args.query else DEMO_QUERIES
    for query in queries:
        print("\n" + "=" * 100)
        print(f"QUESTION: {query}")
        if args.mode == "safe_extract":
            result, answer = ask(query, use_reranker=args.rerank)
        else:
            result = retrieve(query, use_reranker=args.rerank)
            deterministic = answer_from_retrieval(result)
            answer = rewrite_with_local_llm(query, deterministic, result.hits)
        print(f"INTENT: {result.intent.intent}")
        print(f"ANSWER: {answer.answer}")
        print(f"CONFIDENCE: {answer.confidence} | ABSTAIN: {answer.abstain}")
        if answer.missing_data:
            print("MISSING DATA:")
            for item in answer.missing_data:
                print(f"- {item}")
        if answer.caveats:
            print("CAVEATS:")
            for item in answer.caveats:
                print(f"- {item}")
        print("CITATIONS:")
        for citation in answer.citations:
            print(
                f"- {citation.record_id} | {citation.chunk_type} | {citation.source_url} | {citation.chunk_id}"
            )
        print("TOP EVIDENCE:")
        for hit in result.hits[:5]:
            print(f"- rank {hit.final_rank}: {hit.record_id} | {hit.chunk_type} | {hit.why_retrieved}")


if __name__ == "__main__":
    main()
