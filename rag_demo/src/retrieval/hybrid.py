from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from src.chunking.build_chunks import load_chunks
from src.config import CHUNKS_PATH
from src.indexing.build_bm25 import bm25_query
from src.indexing.build_dense_index import dense_query
from src.loaders.family_offices import clean_text, load_family_offices
from src.retrieval.intent import classify_intent, metadata_matches_filters
from src.retrieval.rerank import rerank_hits
from src.schema import Chunk, RetrievalHit, RetrievalResult


def _metadata_from_any(metadata: dict[str, Any]) -> dict[str, Any]:
    parsed = dict(metadata)
    value = parsed.get("source_urls")
    if isinstance(value, str) and value.startswith("["):
        try:
            parsed["source_urls"] = json.loads(value)
        except json.JSONDecodeError:
            parsed["source_urls"] = [value]
    return parsed


def _chunk_to_seed_hit(chunk: Chunk, rank: int, reason: str) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=chunk.chunk_id,
        record_id=chunk.metadata.record_id,
        chunk_type=chunk.metadata.chunk_type,
        text=chunk.text,
        metadata=chunk.metadata.model_dump(mode="json"),
        score=0.0,
        final_rank=rank,
        why_retrieved=reason,
    )


def _to_hit(raw: dict[str, Any], *, source: str) -> RetrievalHit:
    metadata = _metadata_from_any(raw.get("metadata", {}))
    return RetrievalHit(
        chunk_id=clean_text(raw.get("chunk_id")),
        record_id=clean_text(metadata.get("record_id")),
        chunk_type=metadata.get("chunk_type", "record_profile"),
        text=clean_text(raw.get("text")),
        metadata=metadata,
        score=float(raw.get("score", 0.0)),
        dense_rank=int(raw["rank"]) if source == "dense" else None,
        bm25_rank=int(raw["rank"]) if source == "bm25" else None,
        why_retrieved=source,
    )


def _rrf_score(rank: int | None, k: int = 60) -> float:
    if not rank:
        return 0.0
    return 1.0 / (k + rank)


def _field_boost(hit: RetrievalHit, requested_fields: list[str]) -> float:
    field = clean_text(hit.metadata.get("field_name"))
    if field and field in requested_fields:
        return 0.04
    if hit.chunk_type == "contact_policy" and any(
        field in requested_fields
        for field in ["primary_email", "primary_phone", "principal_linkedin_url", "aum_text"]
    ):
        return 0.03
    if hit.chunk_type == "regulatory" and any(
        field in requested_fields for field in ["sec_registered", "sec_crd_number"]
    ):
        return 0.03
    if hit.chunk_type == "recent_activity" and "recent_activity" in requested_fields:
        return 0.03
    return 0.0


def _fuse_hits(
    dense_hits: list[RetrievalHit],
    bm25_hits: list[RetrievalHit],
    *,
    matched_record_ids: list[str],
    preferred_chunk_types: list[str],
    requested_fields: list[str],
) -> list[RetrievalHit]:
    by_id: dict[str, RetrievalHit] = {}
    dense_rank: dict[str, int] = {}
    bm25_rank: dict[str, int] = {}

    for hit in dense_hits:
        by_id[hit.chunk_id] = hit
        dense_rank[hit.chunk_id] = hit.dense_rank or 999
    for hit in bm25_hits:
        if hit.chunk_id in by_id:
            existing = by_id[hit.chunk_id]
            by_id[hit.chunk_id] = existing.model_copy(
                update={
                    "bm25_rank": hit.bm25_rank,
                    "score": max(existing.score, hit.score),
                    "why_retrieved": "dense+bm25",
                }
            )
        else:
            by_id[hit.chunk_id] = hit
        bm25_rank[hit.chunk_id] = hit.bm25_rank or 999

    fused: list[RetrievalHit] = []
    for chunk_id, hit in by_id.items():
        score = _rrf_score(dense_rank.get(chunk_id)) + _rrf_score(bm25_rank.get(chunk_id))
        if hit.record_id in matched_record_ids:
            score += 0.10
        if hit.chunk_type in preferred_chunk_types:
            score += 0.04
        score += _field_boost(hit, requested_fields)
        fused.append(hit.model_copy(update={"score": score}))
    fused.sort(key=lambda item: item.score, reverse=True)
    return [
        hit.model_copy(update={"final_rank": rank})
        for rank, hit in enumerate(fused, start=1)
    ]


def _apply_filters(hits: list[RetrievalHit], filters: dict[str, Any]) -> list[RetrievalHit]:
    if not filters:
        return hits
    return [hit for hit in hits if metadata_matches_filters(hit.metadata, filters)]


def _cap_per_record(hits: list[RetrievalHit], max_chunks_per_record: int) -> list[RetrievalHit]:
    counts: dict[str, int] = defaultdict(int)
    capped: list[RetrievalHit] = []
    for hit in hits:
        if counts[hit.record_id] >= max_chunks_per_record:
            continue
        counts[hit.record_id] += 1
        capped.append(hit)
    return [
        hit.model_copy(update={"final_rank": rank})
        for rank, hit in enumerate(capped, start=1)
    ]


def _seed_filter_listing_hits(chunks: list[Chunk], filters: dict[str, Any], max_records: int = 50) -> list[RetrievalHit]:
    if not filters:
        return []
    seeded: list[RetrievalHit] = []
    seen_records: set[str] = set()
    for chunk in chunks:
        metadata = chunk.metadata.model_dump(mode="json")
        if chunk.metadata.record_id in seen_records:
            continue
        allowed_chunk_types = {"record_profile", "regulatory"}
        if filters.get("has_corporate_linkedin"):
            allowed_chunk_types.add("field_evidence")
        if chunk.metadata.chunk_type not in allowed_chunk_types:
            continue
        if not metadata_matches_filters(metadata, filters):
            continue
        seen_records.add(chunk.metadata.record_id)
        seeded.append(_chunk_to_seed_hit(chunk, len(seeded) + 1, "metadata_filter_match"))
        if len(seeded) >= max_records:
            break
    return seeded


def _seed_matched_record_hits(
    chunks: list[Chunk],
    record_ids: list[str],
    preferred_chunk_types: list[str],
) -> list[RetrievalHit]:
    if not record_ids:
        return []
    chunk_order = [
        *preferred_chunk_types,
        "record_profile",
        "regulatory",
        "contact_policy",
        "recent_activity",
        "field_evidence",
    ]
    by_record: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        if chunk.metadata.record_id in record_ids:
            by_record[chunk.metadata.record_id].append(chunk)

    seeded: list[RetrievalHit] = []
    for record_id in record_ids:
        record_chunks = by_record.get(record_id, [])
        record_chunks.sort(
            key=lambda chunk: (
                chunk_order.index(chunk.metadata.chunk_type)
                if chunk.metadata.chunk_type in chunk_order
                else 999,
                chunk.chunk_id,
            )
        )
        for chunk in record_chunks[:4]:
            seeded.append(_chunk_to_seed_hit(chunk, len(seeded) + 1, "exact_record_match"))
    return seeded


def retrieve(
    query: str,
    *,
    top_k: int = 10,
    dense_top_k: int = 80,
    bm25_top_k: int = 120,
    use_reranker: bool = False,
    include_exact_seeds: bool = True,
    include_filter_seeds: bool = True,
) -> RetrievalResult:
    records = load_family_offices()
    chunks = load_chunks(CHUNKS_PATH)
    intent = classify_intent(query, records)

    if dense_top_k > 0:
        try:
            dense_raw = dense_query(query, top_k=dense_top_k)
        except Exception:
            dense_raw = []
    else:
        dense_raw = []
    if bm25_top_k > 0:
        try:
            bm25_raw = bm25_query(query, top_k=bm25_top_k)
        except Exception:
            bm25_raw = []
    else:
        bm25_raw = []

    dense_hits = [_to_hit(hit, source="dense") for hit in dense_raw]
    bm25_hits = [_to_hit(hit, source="bm25") for hit in bm25_raw]
    fused = _fuse_hits(
        dense_hits,
        bm25_hits,
        matched_record_ids=intent.matched_record_ids,
        preferred_chunk_types=list(intent.preferred_chunk_types),
        requested_fields=intent.requested_fields,
    )
    should_seed_exact = include_exact_seeds and intent.intent != "filtered_listing"
    matched_seeded = (
        _seed_matched_record_hits(
            chunks,
            intent.matched_record_ids,
            list(intent.preferred_chunk_types),
        )
        if should_seed_exact
        else []
    )
    if matched_seeded:
        matched_seeded_ids = {hit.chunk_id for hit in matched_seeded}
        fused = matched_seeded + [hit for hit in fused if hit.chunk_id not in matched_seeded_ids]

    if include_filter_seeds and intent.intent == "filtered_listing":
        seeded = _seed_filter_listing_hits(chunks, intent.filters)
        seeded_ids = {hit.chunk_id for hit in seeded}
        fused = seeded + [hit for hit in fused if hit.chunk_id not in seeded_ids]

    filtered = _apply_filters(fused, intent.filters)
    max_per_record = 4 if intent.intent == "comparison" else 3
    diversified = _cap_per_record(filtered, max_per_record)
    reranked = rerank_hits(query, diversified[: min(12, len(diversified))], enabled=use_reranker)
    tail = diversified[min(12, len(diversified)) :]
    hits = (reranked + tail)[:top_k]
    hits = [
        hit.model_copy(update={"final_rank": rank})
        for rank, hit in enumerate(hits, start=1)
    ]
    return RetrievalResult(query=query, intent=intent, hits=hits)
