from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from src.config import RAW_DATA_PATH


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = clean_text(value).lower()
    return text in {"true", "1", "yes", "y", "registered"}


def to_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    text = clean_text(value)
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def parse_source_urls(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [clean_text(item) for item in value if clean_text(item)]
    text = clean_text(value)
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            parsed = []
        if isinstance(parsed, list):
            return [clean_text(item) for item in parsed if clean_text(item)]
    if "|" in text:
        return [part.strip() for part in text.split("|") if part.strip()]
    if "," in text and "http" in text:
        return [part.strip().strip("'\"") for part in text.split(",") if part.strip()]
    return [text]


def load_family_offices(path: Path = RAW_DATA_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(
            f"Locked dataset not found at {path}. Run scripts/build_all.py or copy the validated "
            "JSON into data/raw/family_offices_validated.json."
        )

    rows = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(rows, list):
        raise ValueError("family_offices_validated.json must contain a JSON list of records.")
    if not rows:
        raise ValueError("family_offices_validated.json is empty.")

    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Record {index} is not a JSON object.")
        record = dict(row)
        record.setdefault("record_id", f"fo_{index:03d}")
        record.setdefault("family_office_name", "")
        if not clean_text(record["family_office_name"]):
            raise ValueError(f"Record {record['record_id']} has no family_office_name.")
        normalized.append(record)
    return normalized

