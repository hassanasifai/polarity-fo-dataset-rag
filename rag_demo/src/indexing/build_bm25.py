from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

from src.chunking.build_chunks import load_chunks
from src.config import BM25_INDEX_PATH
from src.schema import Chunk

TOKEN_RE = re.compile(r"[a-zA-Z0-9@._'-]+")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def build_bm25_index(chunks: list[Chunk] | None = None, path: Path = BM25_INDEX_PATH) -> dict[str, Any]:
    chunks = chunks if chunks is not None else load_chunks()
    if not chunks:
        raise ValueError("Cannot build BM25 index from an empty chunk list.")
    tokenized = [tokenize(chunk.text) for chunk in chunks]
    artifact = {
        "schema_version": 1,
        "position_to_chunk_id": [chunk.chunk_id for chunk in chunks],
        "chunks": [chunk.model_dump(mode="json") for chunk in chunks],
        "tokenized_corpus": tokenized,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    return {"path": str(path), "chunk_count": len(chunks)}


def load_bm25_index(path: Path = BM25_INDEX_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"BM25 index not found at {path}. Run scripts/build_all.py.")
    artifact = json.loads(path.read_text(encoding="utf-8"))
    required = {"schema_version", "position_to_chunk_id", "chunks", "tokenized_corpus"}
    missing = required - set(artifact)
    if missing:
        raise ValueError(f"BM25 artifact missing keys: {sorted(missing)}")
    if artifact["schema_version"] != 1:
        raise ValueError(f"Unsupported BM25 artifact schema version: {artifact['schema_version']}")
    artifact["bm25"] = BM25Okapi(artifact["tokenized_corpus"])
    return artifact


def bm25_query(query: str, top_k: int = 20, path: Path = BM25_INDEX_PATH) -> list[dict[str, Any]]:
    artifact = load_bm25_index(path)
    scores = artifact["bm25"].get_scores(tokenize(query))
    chunks = artifact["chunks"]
    ranked_positions = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
    hits: list[dict[str, Any]] = []
    for rank, position in enumerate(ranked_positions[:top_k], start=1):
        chunk = chunks[position]
        hits.append(
            {
                "chunk_id": artifact["position_to_chunk_id"][position],
                "text": chunk["text"],
                "metadata": chunk["metadata"],
                "rank": rank,
                "score": float(scores[position]),
            }
        )
    return hits

