from __future__ import annotations

from src.config import RERANKER_MODEL
from src.schema import RetrievalHit


def rerank_hits(query: str, hits: list[RetrievalHit], *, enabled: bool = False) -> list[RetrievalHit]:
    if not enabled or len(hits) <= 1:
        return hits
    try:
        from sentence_transformers import CrossEncoder

        model = CrossEncoder(RERANKER_MODEL)
        pairs = [(query, hit.text) for hit in hits]
        scores = model.predict(pairs)
    except Exception:
        return hits

    reranked: list[RetrievalHit] = []
    for hit, score in zip(hits, scores, strict=True):
        reranked.append(hit.model_copy(update={"score": float(score)}))
    reranked.sort(key=lambda hit: hit.score, reverse=True)
    return [
        hit.model_copy(update={"final_rank": rank})
        for rank, hit in enumerate(reranked, start=1)
    ]

