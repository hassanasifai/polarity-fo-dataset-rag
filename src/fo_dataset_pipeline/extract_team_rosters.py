"""Extract named team members + roles from Firecrawl markdown snapshots.

Parses ``firecrawl_exact_sources_full_2026_05_17.json`` and walks every
captured page that looks like a team/leadership/about page. Uses conservative
deterministic patterns: a candidate name must be 2-4 Title-Case tokens, must
not match a banned phrase (page-section headings like "Our Team"), and must be
accompanied by a role line containing a known role keyword.

Output: ``data/processed/team_rosters_raw.csv`` with one row per (FO, name,
role, source_url). This is the seed for Workstream C (principal promotion);
nothing is written into the dataset workbook here.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import pandas as pd
import typer

app = typer.Typer(no_args_is_help=True)

DEFAULT_FIRECRAWL_PATH = Path(
    "data/evidence/firecrawl_exports/2026-05-17/"
    "firecrawl_exact_sources_full_2026_05_17.json"
)
DEFAULT_DATASET_PATH = Path("data/processed/family_offices_validated.csv")
DEFAULT_OUTPUT_PATH = Path("data/processed/team_rosters_raw.csv")

TEAM_PAGE_PATTERNS = re.compile(
    r"/(team|leadership|about|people|partners|firm|our[-_]?team|our[-_]?people|"
    r"who[-_]?we[-_]?are|advisors|founders|management|principals)",
    re.IGNORECASE,
)

# Role-keyword phrases. Each phrase MUST appear at the start of the role string
# (case-insensitive). This is much stricter than substring matching — it avoids
# false positives like "Financial Advisor Magazine" triggering on "advisor".
ROLE_KEYWORDS = (
    "founder", "co-founder", "cofounder",
    "ceo", "cio", "cfo", "coo", "cto",
    "president", "chairman", "chair", "chairperson",
    "managing partner", "managing director", "senior partner", "partner",
    "principal", "vice president",
    "director", "executive director", "senior advisor", "advisor",
    "head of", "trustee",
    "chief executive", "chief investment", "chief financial",
    "chief operating", "chief technology", "chief of staff",
    # Common FO-context prefixes (must still be word-anchored via \b in the
    # ROLE_START_RE so they don't fire on words like "Seniority").
    "senior", "executive", "analyst", "associate", "manager", "lead",
)
ROLE_START_RE = re.compile(
    r"^(?:" + "|".join(re.escape(kw) for kw in ROLE_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

BANNED_NAME_TOKENS = {
    # Section / page headings
    "Our", "Team", "About", "Contact", "Home", "Welcome", "Hello",
    "Press", "Insights", "Resources", "Disclosures", "Careers", "Newsroom",
    "News", "Mission", "Vision", "Values", "History", "Approach",
    "Solutions", "Strategy", "Strategies", "Portfolio", "Privacy", "Policy",
    "Terms", "Use", "Cookies", "Newsletter", "Login", "Sign", "Get", "Learn",
    "Read", "More", "Click", "Toggle", "Menu", "Search", "Skip", "Next",
    "Previous", "Back", "Subscribe", "Submit", "Send",
    # FO industry boilerplate
    "Family", "Office", "Capital", "Investment", "Management", "Wealth",
    "Group", "Partners", "Advisors", "Services", "Firm", "Firms", "Form",
    "Crs", "Adv", "Sec", "Llc", "Inc", "Llp", "Ltd", "Gmbh", "Co",
    "Holdings", "Trust", "Foundation", "Endowment",
    # Generic content words seen in false positives
    "National", "Recognition", "Behind", "Scenes", "Complete", "Agreement",
    "Insurance", "Advisory", "Healthcare", "Advocacy", "Thought", "Leadership",
    "Exceptional", "Talent", "Personal", "Personalized", "Diverse",
    "Specialized", "Excellence", "Tradition", "Generations", "Years",
    "Decades", "Independent", "Privately", "Globally", "Locally",
    # Cities frequently appearing as headings
    "San", "Los", "New", "York", "Francisco", "Angeles", "Chicago", "Boston",
    "Dallas", "Houston", "Atlanta", "Seattle", "Denver", "Miami", "Phoenix",
    "Hong", "Kong", "Singapore", "London", "Paris", "Berlin", "Tokyo",
    "Dubai", "Geneva", "Zurich", "Mumbai", "Sydney",
}

# A name token must be Title-Case, ≥3 chars after the leading capital (so "Jo"
# is allowed but "Mr" is not), OR a single-letter middle initial like "W.".
NAME_TOKEN_RE = re.compile(r"^(?:[A-Z][a-zA-Z'’\-]{1,}|[A-Z]\.)$")
# Whole line that is ONLY a name (used for heading detection). No commas, no
# brackets, no extra text.
NAME_ONLY_RE = re.compile(
    r"^[A-Z][a-zA-Z'’\-]+(?:\s+(?:[A-Z][a-zA-Z'’\-\.]+|[A-Z]\.)){1,3}$"
)
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
# Bold name + immediate role on same line. The role MUST start with a role keyword
# (enforced by ROLE_START_RE) and be ≤60 chars.
BOLD_NAME_RE = re.compile(
    r"\*\*\s*([A-Z][a-zA-Z'’\-]+(?:\s+(?:[A-Z][a-zA-Z'’\-\.]+|[A-Z]\.)){1,3})\s*\*\*"
    r"\s*[,\-\—:]\s*([^\*\n\[\]]{1,80})"
)


def _is_role_line(text: str) -> bool:
    cleaned = re.sub(r"[\[\]\(\)]", "", text).strip()
    if not cleaned:
        return False
    if len(cleaned) > 80:
        return False
    return bool(ROLE_START_RE.match(cleaned))


def _is_plausible_name(candidate: str) -> bool:
    candidate = candidate.strip()
    if not NAME_ONLY_RE.match(candidate):
        return False
    tokens = candidate.split()
    if not (2 <= len(tokens) <= 4):
        return False
    if any(token in BANNED_NAME_TOKENS for token in tokens):
        return False
    if any(token.isupper() and len(token) > 1 and not token.endswith(".") for token in tokens):
        return False
    # Reject if any token fails the strict per-token shape (catches "MBA", "RIA").
    if not all(NAME_TOKEN_RE.match(token) for token in tokens):
        return False
    return True


def _normalize_role(text: str) -> str:
    # Strip URLs entirely (and the trailing markdown-link closer that often
    # precedes them, e.g. "Chief Executive Officer](https://...)" ).
    cleaned = re.sub(r"\]\(?https?://\S+\)?", "", text)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    # Strip markdown line-continuation backslashes.
    cleaned = cleaned.replace("\\\\", " ").replace("\\", " ")
    # Strip bracketed link-text leftovers.
    cleaned = re.sub(r"[\[\]\(\)]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,-—:;.")
    return cleaned[:80]


def _domain(url: object) -> str:
    if url is None:
        return ""
    text = str(url).strip()
    if not text or "://" not in text:
        return ""
    return urlparse(text).netloc.lower().removeprefix("www.")


BOLD_ANYWHERE_RE = re.compile(
    r"\*\*\s*([A-Z][a-zA-Z'’\-]+(?:\s+(?:[A-Z][a-zA-Z'’\-\.]+|[A-Z]\.)){1,3})\s*\*\*"
)


def _scan_for_role(lines: list[str], start: int, max_blank_skips: int) -> str | None:
    """Walk forward from ``start`` (exclusive) and return the first role line.

    Stops at the next bold-name to avoid bleeding into the following person's
    role (the source markdown sometimes omits roles for individual people).
    """
    scanned = 0
    for follower in lines[start : start + 10]:
        if BOLD_ANYWHERE_RE.search(follower):
            return None
        stripped = follower.strip().lstrip("*_-•\\ ").strip()
        stripped = re.sub(r"\*\*", "", stripped).strip()
        if not stripped:
            continue
        scanned += 1
        if _is_role_line(stripped):
            return stripped
        if scanned >= max_blank_skips:
            break
    return None


def extract_from_markdown(markdown: str) -> list[tuple[str, str]]:
    """Return de-duplicated (name, role) pairs found in the markdown text.

    Three patterns are supported (high precision, low recall by design):

    1. Bold name + role on same line after a separator, e.g.
       ``**Jane Doe**, Managing Partner``.
    2. Bold name on its own (or with stray markdown), role on next non-blank
       line within 5 lines — handles Verlinvest-style team grids.
    3. Heading or plain-name line containing only a name, role on the next
       non-blank line — handles Haven-style profile blocks.
    """
    found: dict[str, str] = {}
    lines = markdown.splitlines()

    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue

        # Pattern 1 + 2: bold-name anywhere on this line.
        for match in BOLD_ANYWHERE_RE.finditer(line):
            candidate_name = match.group(1).strip()
            if not _is_plausible_name(candidate_name):
                continue
            tail = line[match.end():].lstrip(" \\,-—:")[:80]
            if tail and _is_role_line(tail):
                found.setdefault(candidate_name, _normalize_role(tail))
                continue
            role = _scan_for_role(lines, index + 1, max_blank_skips=5)
            if role:
                found.setdefault(candidate_name, _normalize_role(role))

        # Pattern 3a: heading line is a name.
        heading_match = HEADING_RE.match(line)
        if heading_match:
            cleaned = re.sub(r"\*\*", "", heading_match.group(1)).strip()
            if _is_plausible_name(cleaned) and cleaned not in found:
                role = _scan_for_role(lines, index + 1, max_blank_skips=3)
                if role:
                    found.setdefault(cleaned, _normalize_role(role))
            continue

        # Pattern 3b: plain line is a name on its own.
        if NAME_ONLY_RE.match(line) and _is_plausible_name(line) and line not in found:
            role = _scan_for_role(lines, index + 1, max_blank_skips=2)
            if role:
                found.setdefault(line, _normalize_role(role))

    return list(found.items())


def _build_domain_to_record(dataset_df: pd.DataFrame) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for row in dataset_df.to_dict(orient="records"):
        domain = _domain(row.get("website_url"))
        if domain:
            lookup.setdefault(domain, row)
    return lookup


@app.command("run")
def run_extraction(
    firecrawl_path: Annotated[
        Path, typer.Option("--firecrawl-path")
    ] = DEFAULT_FIRECRAWL_PATH,
    dataset_path: Annotated[Path, typer.Option("--dataset")] = DEFAULT_DATASET_PATH,
    output_path: Annotated[Path, typer.Option("--output")] = DEFAULT_OUTPUT_PATH,
) -> None:
    """Extract team rosters from Firecrawl markdown into a CSV seed file."""
    if not firecrawl_path.exists():
        raise typer.BadParameter(f"firecrawl export not found: {firecrawl_path}")
    if not dataset_path.exists():
        raise typer.BadParameter(f"dataset not found: {dataset_path}")

    raw = json.loads(firecrawl_path.read_text(encoding="utf-8"))
    docs = raw.get("data", []) if isinstance(raw, dict) else raw

    dataset_df = pd.read_csv(dataset_path).fillna("")
    domain_to_record = _build_domain_to_record(dataset_df)

    rows: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    docs_scanned = 0
    team_pages = 0

    for doc in docs:
        markdown = doc.get("markdown") or ""
        metadata = doc.get("metadata") or {}
        source_url = (
            metadata.get("sourceURL")
            or metadata.get("url")
            or ""
        )
        if not markdown or not source_url:
            continue
        docs_scanned += 1

        page_domain = _domain(source_url)
        record = domain_to_record.get(page_domain)
        if record is None:
            continue

        # Restrict to pages that look like team/leadership/about — skip generic pages
        # unless the page already has bold-name role patterns.
        if not TEAM_PAGE_PATTERNS.search(source_url):
            # Allow homepages where the markdown contains explicit role keywords
            # alongside named people (some FOs put bios on the homepage). Be strict.
            if not BOLD_NAME_RE.search(markdown):
                continue
        else:
            team_pages += 1

        for name, role in extract_from_markdown(markdown):
            dedupe_key = (str(record.get("record_id")), name.lower(), role.lower())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rows.append(
                {
                    "record_id": record.get("record_id", ""),
                    "family_office_name": record.get("family_office_name", ""),
                    "principal_name": name,
                    "principal_role": role,
                    "source_url": source_url,
                    "extraction_method": "firecrawl_markdown_pattern_match",
                }
            )

    out_df = pd.DataFrame(
        rows,
        columns=[
            "record_id",
            "family_office_name",
            "principal_name",
            "principal_role",
            "source_url",
            "extraction_method",
        ],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(output_path, index=False)

    fo_count = out_df["record_id"].nunique() if not out_df.empty else 0
    typer.echo(
        f"Scanned {docs_scanned} Firecrawl docs ({team_pages} matched team-page URLs). "
        f"Extracted {len(out_df)} team members across {fo_count} FOs. "
        f"Output: {output_path}."
    )


if __name__ == "__main__":
    app()
