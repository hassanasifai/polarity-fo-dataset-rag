"""Lightweight secret scan for the public Task 1 repository.

This is not a replacement for a full-history scanner such as gitleaks, but it
keeps CI from passing if obvious live-token patterns appear in committed text.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "data/index",
    "rag_demo/data/index",
}

SKIP_SUFFIXES = {
    ".bin",
    ".db",
    ".dll",
    ".exe",
    ".jpg",
    ".jpeg",
    ".mp4",
    ".pdf",
    ".pkl",
    ".png",
    ".pyc",
    ".sqlite3",
    ".xlsx",
}

PATTERNS = {
    "generic_assignment": re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"
    ),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "apify_token": re.compile(r"\bapify_api_[A-Za-z0-9]{20,}\b", re.IGNORECASE),
}


def _is_skipped(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if any(rel == skip or rel.startswith(f"{skip}/") for skip in SKIP_DIRS):
        return True
    return path.suffix.lower() in SKIP_SUFFIXES


def main() -> int:
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or _is_skipped(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "example" in line.lower() or "placeholder" in line.lower():
                continue
            for name, pattern in PATTERNS.items():
                if pattern.search(line):
                    rel = path.relative_to(ROOT).as_posix()
                    findings.append(f"{rel}:{lineno}: possible {name}")

    if findings:
        print("Potential secrets found:")
        for finding in findings:
            print(f"  - {finding}")
        return 1
    print("Secret scan passed: no obvious token patterns found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
