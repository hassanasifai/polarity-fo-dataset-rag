from __future__ import annotations

import hashlib
import json
import math
import shutil
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from src.chunking.build_chunks import load_chunks
from src.config import (
    CHROMA_COLLECTION,
    CHROMA_DIR,
    DEFAULT_EMBEDDING_MODEL,
    FALLBACK_EMBEDDING_MODEL,
)
from src.schema import Chunk


class Embedder(Protocol):
    model_name: str
    dimension: int

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    def encode_query(self, text: str) -> list[float]:
        ...


class HashingEmbedder:
    """Deterministic local fallback used only when sentence-transformer models are unavailable."""

    model_name = "hashing-local-fallback"
    dimension = 384

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def encode_query(self, text: str) -> list[float]:
        return self._embed(text)


@lru_cache(maxsize=6)
def _cached_sentence_transformer(model_name: str, local_files_only: bool) -> Any:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name, local_files_only=local_files_only)


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str, *, local_files_only: bool = False) -> None:
        self.model_name = model_name
        self.model = _cached_sentence_transformer(model_name, local_files_only)
        if hasattr(self.model, "get_embedding_dimension"):
            dimension = self.model.get_embedding_dimension()
        else:
            dimension = self.model.get_sentence_embedding_dimension()
        self.dimension = int(dimension or 384)

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        if hasattr(self.model, "encode_document"):
            embeddings = self.model.encode_document(texts, normalize_embeddings=True)
        else:
            embeddings = self.model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def encode_query(self, text: str) -> list[float]:
        if hasattr(self.model, "encode_query"):
            embedding = self.model.encode_query([text], normalize_embeddings=True)[0]
        else:
            embedding = self.model.encode([text], normalize_embeddings=True)[0]
        return embedding.tolist()


def load_embedder(
    preferred_model: str | None = None,
    *,
    allow_hashing: bool = True,
    local_files_only: bool = False,
) -> Embedder:
    if preferred_model == HashingEmbedder.model_name:
        return HashingEmbedder()

    model_candidates = [preferred_model] if preferred_model else [DEFAULT_EMBEDDING_MODEL]
    if preferred_model is None and FALLBACK_EMBEDDING_MODEL not in model_candidates:
        model_candidates.append(FALLBACK_EMBEDDING_MODEL)

    errors: list[str] = []
    for model_name in model_candidates:
        try:
            return SentenceTransformerEmbedder(model_name, local_files_only=local_files_only)
        except Exception as exc:  # pragma: no cover - depends on local model/cache state
            errors.append(f"{model_name}: {type(exc).__name__}: {exc}")

    if allow_hashing:
        return HashingEmbedder()
    raise RuntimeError("Could not load a local embedding model. " + " | ".join(errors))


def _chunk_metadata_for_chroma(chunk: Chunk) -> dict[str, str | int | float | bool]:
    metadata = chunk.metadata.model_dump(mode="json")
    chroma_metadata: dict[str, str | int | float | bool] = {}
    for key, value in metadata.items():
        if isinstance(value, list):
            chroma_metadata[key] = json.dumps(value)
        elif value is None:
            chroma_metadata[key] = ""
        elif isinstance(value, (str, int, float, bool)):
            chroma_metadata[key] = value
        else:
            chroma_metadata[key] = json.dumps(value, default=str)
    return chroma_metadata


def _batch(items: list[Any], size: int) -> Iterable[list[Any]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _get_chroma_client() -> Any:
    import chromadb
    from chromadb.config import Settings

    return chromadb.PersistentClient(
        path=str(CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False),
    )


def reset_dense_index() -> None:
    if CHROMA_DIR.exists():
        shutil.rmtree(CHROMA_DIR)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)


def build_dense_index(chunks: list[Chunk] | None = None, *, model_name: str | None = None) -> dict[str, Any]:
    chunks = chunks if chunks is not None else load_chunks()
    if not chunks:
        raise ValueError("Cannot build dense index from an empty chunk list.")

    reset_dense_index()
    embedder = load_embedder(model_name)
    client = _get_chroma_client()
    collection = client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        metadata={
            "hnsw:space": "cosine",
            "embedding_model": embedder.model_name,
            "embedding_dimension": embedder.dimension,
        },
        embedding_function=None,
    )

    ids = [chunk.chunk_id for chunk in chunks]
    documents = [chunk.text for chunk in chunks]
    metadatas = [_chunk_metadata_for_chroma(chunk) for chunk in chunks]
    embeddings = embedder.encode_documents(documents)

    for id_batch, doc_batch, meta_batch, embedding_batch in zip(
        _batch(ids, 64),
        _batch(documents, 64),
        _batch(metadatas, 64),
        _batch(embeddings, 64),
        strict=True,
    ):
        collection.add(
            ids=id_batch,
            documents=doc_batch,
            metadatas=meta_batch,
            embeddings=embedding_batch,
        )

    return {
        "collection": CHROMA_COLLECTION,
        "path": str(CHROMA_DIR),
        "chunk_count": len(chunks),
        "embedding_model": embedder.model_name,
        "embedding_dimension": embedder.dimension,
    }


def load_dense_collection() -> Any:
    if not CHROMA_DIR.exists():
        raise FileNotFoundError(f"Chroma index not found at {CHROMA_DIR}. Run scripts/build_all.py.")
    client = _get_chroma_client()
    return client.get_collection(name=CHROMA_COLLECTION, embedding_function=None)


def dense_query(query: str, top_k: int = 20, *, model_name: str | None = None) -> list[dict[str, Any]]:
    collection = load_dense_collection()
    manifest_model = model_name or (collection.metadata or {}).get("embedding_model")
    embedder = load_embedder(
        manifest_model,
        allow_hashing=manifest_model in {None, "hashing-local-fallback"},
        local_files_only=True,
    )
    query_embedding = embedder.encode_query(query)
    results = collection.query(query_embeddings=[query_embedding], n_results=top_k)

    hits: list[dict[str, Any]] = []
    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    for rank, (chunk_id, text, metadata, distance) in enumerate(
        zip(ids, docs, metadatas, distances, strict=True),
        start=1,
    ):
        hits.append(
            {
                "chunk_id": chunk_id,
                "text": text,
                "metadata": metadata or {},
                "rank": rank,
                "score": 1.0 / (1.0 + float(distance)),
            }
        )
    return hits


def collection_count(path: Path = CHROMA_DIR) -> int:
    if not path.exists():
        return 0
    collection = load_dense_collection()
    return int(collection.count())
