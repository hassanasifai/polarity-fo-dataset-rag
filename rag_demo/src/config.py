from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]

DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
INDEX_DIR = DATA_DIR / "index"
CHROMA_DIR = INDEX_DIR / "chroma"
BM25_DIR = INDEX_DIR / "bm25"
REPORTS_DIR = ROOT_DIR / "reports"

RAW_DATA_PATH = RAW_DIR / "family_offices_validated.json"
UPSTREAM_JSON_PATH = (
    ROOT_DIR / "fo_dataset_pipeline" / "data" / "processed" / "family_offices_validated.json"
)
UPSTREAM_XLSX_PATH = (
    ROOT_DIR / "fo_dataset_pipeline" / "data" / "processed" / "family_offices_validated.xlsx"
)

CHUNKS_PATH = PROCESSED_DIR / "chunks.jsonl"
GOLDEN_EVAL_PATH = PROCESSED_DIR / "golden_eval.jsonl"
MANIFEST_PATH = PROCESSED_DIR / "rag_manifest.json"
BM25_INDEX_PATH = BM25_DIR / "bm25_index.pkl"
CHROMA_COLLECTION = "polarityiq_family_offices"

DEFAULT_EMBEDDING_MODEL = os.getenv("POLARITYIQ_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
FALLBACK_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
HIGH_END_EMBEDDING_MODEL = "BAAI/bge-m3"
RERANKER_MODEL = os.getenv("POLARITYIQ_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L6-v2")
OLLAMA_MODEL = os.getenv("POLARITYIQ_OLLAMA_MODEL", "llama3.1")

SENSITIVE_FIELDS = {
    "primary_email",
    "primary_phone",
    "principal_linkedin_url",
    "aum_text",
    "sec_registered",
    "sec_crd_number",
    "recent_activity",
}

DEMO_QUERIES = [
    "What type of family office is Cat Trail Capital and where is it based?",
    "Show me the evidence for Ohana Advisors' SEC registration.",
    "Which SEC-registered family offices in California are in the dataset?",
    "What recent activity is recorded for Pathstone?",
    "Do we have a direct phone number for Ralph Family Office?",
    "Compare Cat Trail Capital and Ohana Advisors on type, geography, SEC status, and contact availability.",
    "What is the AUM of Cat Trail Capital?",
]


def ensure_directories() -> None:
    for path in [RAW_DIR, PROCESSED_DIR, CHROMA_DIR, BM25_DIR, REPORTS_DIR]:
        path.mkdir(parents=True, exist_ok=True)
