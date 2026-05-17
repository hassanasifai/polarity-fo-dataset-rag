from __future__ import annotations

import json
import re
from urllib.parse import urlparse

import requests

from src.config import OLLAMA_MODEL
from src.schema import AnswerResult, RetrievalHit

LOCAL_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"


def _allowed_local_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}


def _tokens_that_look_sensitive(text: str) -> set[str]:
    emails = set(re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text))
    phones = set(re.findall(r"\+?\d[\d().\-\s]{7,}\d", text))
    urls = set(re.findall(r"https?://[^\s)]+", text))
    return emails | phones | urls


def _serialize_evidence(hits: list[RetrievalHit]) -> str:
    payload = [
        {
            "record_id": hit.record_id,
            "chunk_id": hit.chunk_id,
            "chunk_type": hit.chunk_type,
            "text": hit.text,
            "source_urls": hit.metadata.get("source_urls"),
            "uncertainty_notes": hit.metadata.get("uncertainty_notes"),
        }
        for hit in hits[:8]
    ]
    return json.dumps(payload, indent=2)


def rewrite_with_local_llm(
    query: str,
    deterministic: AnswerResult,
    evidence: list[RetrievalHit],
    *,
    ollama_url: str = LOCAL_OLLAMA_URL,
    model: str = OLLAMA_MODEL,
) -> AnswerResult:
    if not _allowed_local_url(ollama_url):
        return deterministic.model_copy(
            update={
                "caveats": [
                    *deterministic.caveats,
                    "Local LLM URL was rejected because it is not loopback.",
                ]
            }
        )

    prompt = f"""
You rewrite an already validated answer. You may not add new facts.
If the evidence does not support a claim, keep the deterministic answer unchanged.
Return only concise prose, no JSON.

Question:
{query}

Deterministic answer:
{deterministic.answer}

Evidence:
{_serialize_evidence(evidence)}
""".strip()

    try:
        response = requests.post(
            ollama_url,
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=20,
        )
        response.raise_for_status()
        rewritten = str(response.json().get("response", "")).strip()
    except requests.RequestException:
        return deterministic.model_copy(
            update={
                "caveats": [
                    *deterministic.caveats,
                    "Ollama was unavailable; deterministic extractive answer returned.",
                ]
            }
        )

    if not rewritten:
        return deterministic

    allowed_sensitive = _tokens_that_look_sensitive(deterministic.answer)
    new_sensitive = _tokens_that_look_sensitive(rewritten) - allowed_sensitive
    if new_sensitive:
        return deterministic.model_copy(
            update={
                "caveats": [
                    *deterministic.caveats,
                    "Local LLM rewrite was rejected because it introduced uncited sensitive-looking text.",
                ]
            }
        )

    return deterministic.model_copy(
        update={
            "answer": rewritten,
            "caveats": [
                *deterministic.caveats,
                "Answer wording was rewritten by local Ollama from already-selected evidence only.",
            ],
        }
    )
