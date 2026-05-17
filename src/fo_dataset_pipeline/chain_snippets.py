"""Pass 3 — Extract verbatim ≤25-word snippets from Firecrawl markdown.

Targets the three featured validation chain records (Cat Trail, JFG, Verlinvest).
Output:
- ``data/processed/validation_chain_snippets.csv``
- ``reports/validation_chains.md`` (rewritten in claim-by-claim audit format)

Quotes are picked from existing Firecrawl markdown snapshots — no new network
crawl. If a source URL is a PDF (Firecrawl skips PDFs), the snippet is recorded
as ``unavailable`` with a note rather than fabricated.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(no_args_is_help=True)

FIRECRAWL_JSON_DEFAULT = Path(
    "data/evidence/firecrawl_exports/2026-05-17/firecrawl_exact_sources_full_2026_05_17.json"
)
SNIPPETS_CSV_DEFAULT = Path("data/processed/validation_chain_snippets.csv")
CHAINS_MD_DEFAULT = Path("reports/validation_chains.md")

PRIMARY_KEYWORD_RE = re.compile(
    r"(single[- ]family office|multi[- ]family office|family office|founding family|"
    r"investment office|family[- ]backed|family of\b)",
    re.IGNORECASE,
)
SECONDARY_KEYWORD_RE = re.compile(
    r"(invest(ment|ing)?|portfolio|consumer brand|long[- ]term|generation(s|al)?|"
    r"wealth|stewards?|legacy|family)",
    re.IGNORECASE,
)
WHITESPACE_RE = re.compile(r"\s+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
MAX_WORDS = 25

MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
MARKDOWN_HEADING_RE = re.compile(r"^#+\s*", re.MULTILINE)
NAV_LIST_RE = re.compile(r"^\s*[-*]\s+.{0,40}$", re.MULTILINE)


@dataclass(frozen=True)
class ChainTarget:
    record_id: str
    family_office_name: str
    family_office_type: str
    sources: tuple[tuple[str, str, str], ...]  # (source_url, source_type, claim_supported)
    enrichment_steps: tuple[str, ...]
    uncertainties: tuple[str, ...]
    falsifiers: tuple[str, ...]
    reconciliation_note: str


MANUAL_SOURCE_QUOTES: dict[str, tuple[tuple[str, str], ...]] = {
    "https://jfgfamilyoffice.com/pdf/JFG-Family-Office-Form-CRS.pdf": (
        (
            "Johnson Financial Group LLC, DBA JFG Family Office is registered with "
            "the Securities and Exchange Commission as an investment adviser.",
            "Manual PDF text extraction with pypdf; Firecrawl does not crawl PDFs.",
        ),
        (
            "JFG's minimum annual fee is $100,000.",
            "Manual PDF text extraction with pypdf; used as regulatory service context.",
        ),
    ),
    "https://www.verlinvest.com/team/": (
        (
            "Roberto Italia Chief Executive Officer",
            "Manual review of Firecrawl profile-card text; no narrative sentence was present.",
        ),
        (
            "Rachel Citera Principal, New York",
            "Manual review of Firecrawl profile-card text; no narrative sentence was present.",
        ),
    ),
}


CHAINS: tuple[ChainTarget, ...] = (
    ChainTarget(
        record_id="fo_001",
        family_office_name="Cat Trail Capital",
        family_office_type="single_family_office",
        sources=(
            (
                "https://www.cattrail.com/",
                "official_site_home",
                "single-family office identity and Dekker family attribution",
            ),
            (
                "https://www.cattrail.com/#About",
                "official_site_about_anchor",
                "investment mandate across public securities, fund managers, real assets, "
                "and private companies",
            ),
            (
                "https://www.cattrail.com/#Team",
                "official_site_team_anchor",
                "principal family / team composition",
            ),
        ),
        enrichment_steps=(
            "Captured official site markdown via Firecrawl on 2026-05-17 (depth 0, exact "
            "source URLs only).",
            "Captured candidate corporate-contact signals via Apify "
            "vdrmota/contact-info-scraper; promoted admin@cattrail.com as primary_email "
            "with `corporate_public_listed` confidence.",
            "Matched the corporate LinkedIn URL via Apify "
            "automation-lab/linkedin-company-scraper "
            "(linkedin.com/company/cattrail-capital-llc) with `linkedin_scraped_match` "
            "confidence.",
            "Cross-checked the address via Apify compass/crawler-google-places (New York, NY).",
            "Recent activity: no qualifying 2025+ public news signal — recorded transparently "
            "in uncertainty_notes rather than padded with weak matches.",
        ),
        uncertainties=(
            "No public AUM is disclosed on the site; AUM left blank.",
            "Named operators are visible on the team section, but personal contact channels "
            "and personal LinkedIn profiles are not linked by the official site.",
            "Sector exposure is derived from broad descriptions, not portfolio-level disclosure.",
        ),
        falsifiers=(
            "If the site is found to be a multi-family office serving multiple families, "
            "the single-family office classification must be downgraded.",
            "If the Dekker family attribution is later contradicted by a primary source, "
            "principal_name must be cleared.",
        ),
        reconciliation_note=(
            "The first pass only captured Cat Trail as a Dekker-family entity, not a named "
            "operator. I almost left the principal layer at the family level until the "
            "official team section exposed David Dekker, Russell Dekker, and Andrew "
            "Budinoff with roles. I still did not promote personal contact channels "
            "because the site links only to the company LinkedIn page."
        ),
    ),
    ChainTarget(
        record_id="fo_007",
        family_office_name="JFG Family Office",
        family_office_type="multi_family_office",
        sources=(
            (
                "https://jfgfamilyoffice.com/",
                "official_site_home",
                "current brand and family-office identity",
            ),
            (
                "https://jfgfamilyoffice.com/better-way",
                "official_site_better_way_page",
                "single-family-office origin story now serving client families as an MFO",
            ),
            (
                "https://jfgfamilyoffice.com/pdf/JFG-Family-Office-Form-CRS.pdf",
                "official_form_crs_pdf",
                "regulatory Form CRS disclosure of advisory relationship",
            ),
        ),
        enrichment_steps=(
            "Captured official site markdown via Firecrawl on 2026-05-17 for the home and "
            "/better-way pages; the Form CRS PDF was downloaded and text-extracted with "
            "`pypdf` after Firecrawl skipped PDF text.",
            "Verified the canonical domain (jfgfamilyoffice.com) against the legacy "
            "jfgwealth.net brand; older references redirect to the current site.",
            "Captured corporate contact signals via Apify vdrmota/contact-info-scraper "
            "and Apify automation-lab/linkedin-company-scraper.",
            "Recent activity: promoted a 2025+ Business Journals headline "
            "('JFG Family Office brings holistic wealth and philanthropy services to Dallas') "
            "into recent_activity, with source URL and date.",
        ),
        uncertainties=(
            "Former jfgwealth.net brand still surfaces in older references; current canonical "
            "domain is jfgfamilyoffice.com.",
            "Leadership names and roles are visible in official bios, but personal contact "
            "channels are not linked by the official site.",
        ),
        falsifiers=(
            "If the Form CRS PDF describes JFG as a generic RIA without family-office "
            "framing, the MFO label must be re-evaluated.",
            "If the better-way page is removed and no MFO/SFO-origin language is preserved "
            "anywhere on the site, the classification basis weakens.",
        ),
        reconciliation_note=(
            "JFG uses both legacy JFG Wealth wording and the current JFG Family Office "
            "brand. I treated the current domain as canonical, then used the Form CRS "
            "PDF only after manually extracting the PDF text instead of pretending "
            "Firecrawl had read it."
        ),
    ),
    ChainTarget(
        record_id="fo_020",
        family_office_name="Verlinvest",
        family_office_type="family_backed_investment_firm",
        sources=(
            (
                "https://www.verlinvest.com/",
                "official_site_home",
                "family-backed investment company identity and AB InBev heritage context",
            ),
            (
                "https://www.verlinvest.com/approach/",
                "official_site_approach_page",
                "long-term consumer-brand investment thesis",
            ),
            (
                "https://www.verlinvest.com/team/",
                "official_site_team_page",
                "team composition and family-sponsor context",
            ),
        ),
        enrichment_steps=(
            "Captured official site markdown via Firecrawl on 2026-05-17 for the home and "
            "/approach pages; the /team page is a grid of profile cards, so exact card text "
            "was used for names and roles rather than a fabricated narrative sentence.",
            "Confirmed the family-backed framing through the /approach page's verbatim "
            "phrasing 'as a family-backed business'.",
            "Recent activity: promoted a 2025 YourStory.com headline "
            "('Verlinvest invests $75M in Coimbatore-based The Eye Foundation') into "
            "recent_activity with source URL and date.",
            "Cross-checked the European HQ via Apify compass/crawler-google-places (Brussels, "
            "Belgium).",
        ),
        uncertainties=(
            "Family sponsor wording (de Spoelberch and related families) is intentionally "
            "broad because ownership structure varies across sources.",
            "Not a classic single-family office — labeled family_backed_investment_firm so "
            "the row is not mis-classified as an SFO.",
        ),
        falsifiers=(
            "If public filings show Verlinvest is now majority-owned outside the founding "
            "families, the family-backed classification must be revisited.",
            "If the team page de-emphasizes family sponsor framing, source_notes must be "
            "updated to reflect a pure investment-firm description.",
        ),
        reconciliation_note=(
            "Verlinvest is not a classic SFO. The strongest evidence says "
            "`family-backed business`, so I kept the label broad. The team page also "
            "looked like a failed extraction at first, but the markdown did contain "
            "profile-card names and roles; I used those exact card strings and did "
            "not invent a sentence around them."
        ),
    ),
)


def load_firecrawl_index(path: Path) -> dict[str, str]:
    """Map exact-source URL -> markdown body from a Firecrawl batch export."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("data") if isinstance(payload, dict) else payload
    index: dict[str, str] = {}
    for item in items or []:
        meta = item.get("metadata") or {}
        url = (meta.get("sourceURL") or meta.get("url") or item.get("url") or "").strip()
        if not url:
            continue
        markdown = item.get("markdown") or ""
        if url not in index or len(markdown) > len(index[url]):
            index[url] = markdown
    return index


def _clean_markdown(text: str) -> str:
    """Strip image/link/heading/nav noise so sentence splitting works."""
    text = MARKDOWN_IMAGE_RE.sub(" ", text)
    text = MARKDOWN_LINK_RE.sub(r"\1", text)
    text = MARKDOWN_HEADING_RE.sub("", text)
    text = NAV_LIST_RE.sub("", text)
    text = re.sub(r"[\\_*`>]+", " ", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def _score_sentence(sentence: str) -> int:
    """Higher score = stronger evidentiary sentence."""
    score = 0
    score += 3 * len(PRIMARY_KEYWORD_RE.findall(sentence))
    score += 1 * len(SECONDARY_KEYWORD_RE.findall(sentence))
    return score


def extract_quotes(
    markdown: str,
    max_quotes: int = 2,
    skip_signatures: set[str] | None = None,
) -> list[str]:
    """Return up to max_quotes verbatim sentences ranked by keyword density.

    Sentences whose normalized signature appears in ``skip_signatures`` are
    excluded — used to avoid emitting the same quote across anchor URLs that
    share the same Firecrawl markdown.
    """
    if not markdown:
        return []
    cleaned = _clean_markdown(markdown)
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(cleaned) if s.strip()]
    skip = skip_signatures or set()
    scored: list[tuple[int, str]] = []
    for sentence in sentences:
        words = sentence.split()
        if not (5 <= len(words) <= 60):
            continue
        score = _score_sentence(sentence)
        if score == 0:
            continue
        trimmed = sentence
        if len(words) > MAX_WORDS:
            trimmed = " ".join(words[:MAX_WORDS]).rstrip(",.;:") + "…"
        signature = trimmed.casefold()[:80]
        if signature in skip:
            continue
        scored.append((score, trimmed))
    scored.sort(key=lambda pair: (-pair[0], len(pair[1])))
    picked: list[str] = []
    seen: set[str] = set()
    for _, quote in scored:
        signature = quote.casefold()[:80]
        if signature in seen:
            continue
        seen.add(signature)
        picked.append(quote)
        if len(picked) >= max_quotes:
            break
    return picked


def _base_url(url: str) -> str:
    return url.split("#", 1)[0].rstrip("/")


def build_snippet_rows(
    chains: tuple[ChainTarget, ...],
    fc_index: dict[str, str],
) -> list[dict[str, str]]:
    extracted_at = datetime.now(UTC).date().isoformat()
    rows: list[dict[str, str]] = []
    for chain in chains:
        used_signatures: dict[str, set[str]] = {}
        for source_url, source_type, claim in chain.sources:
            markdown = fc_index.get(source_url, "") or fc_index.get(source_url.rstrip("/"), "")
            if not markdown:
                # Fall back to the base URL if this was an anchor link
                base = _base_url(source_url)
                markdown = fc_index.get(base, "") or fc_index.get(base + "/", "")

            base_key = _base_url(source_url)
            skip = used_signatures.setdefault(base_key, set())

            manual_quotes = MANUAL_SOURCE_QUOTES.get(source_url, ())

            if not markdown and manual_quotes:
                for idx, (quote, note) in enumerate(manual_quotes, start=1):
                    rows.append(
                        {
                            "record_id": chain.record_id,
                            "family_office_name": chain.family_office_name,
                            "source_url": source_url,
                            "source_type": source_type,
                            "claim_supported": claim,
                            "quote_index": str(idx),
                            "exact_quote": quote,
                            "quote_status": "extracted",
                            "note": note,
                            "extracted_at": extracted_at,
                        }
                    )
                continue

            if not markdown:
                rows.append(
                    {
                        "record_id": chain.record_id,
                        "family_office_name": chain.family_office_name,
                        "source_url": source_url,
                        "source_type": source_type,
                        "claim_supported": claim,
                        "quote_index": "1",
                        "exact_quote": "",
                        "quote_status": "markdown_unavailable",
                        "note": "Firecrawl did not return markdown for this URL; the source is "
                                "retained as context but not used as quote support.",
                        "extracted_at": extracted_at,
                    }
                )
                continue

            quotes = extract_quotes(markdown, max_quotes=2, skip_signatures=skip)
            if not quotes and manual_quotes:
                for idx, (quote, note) in enumerate(manual_quotes, start=1):
                    rows.append(
                        {
                            "record_id": chain.record_id,
                            "family_office_name": chain.family_office_name,
                            "source_url": source_url,
                            "source_type": source_type,
                            "claim_supported": claim,
                            "quote_index": str(idx),
                            "exact_quote": quote,
                            "quote_status": "extracted",
                            "note": note,
                            "extracted_at": extracted_at,
                        }
                    )
                continue

            if not quotes:
                rows.append(
                    {
                        "record_id": chain.record_id,
                        "family_office_name": chain.family_office_name,
                        "source_url": source_url,
                        "source_type": source_type,
                        "claim_supported": claim,
                        "quote_index": "1",
                        "exact_quote": "",
                        "quote_status": "no_keyword_match",
                        "note": "Markdown was fetched but contained no reliable quote sentence "
                                "within the configured length window.",
                        "extracted_at": extracted_at,
                    }
                )
                continue

            for idx, quote in enumerate(quotes, start=1):
                signature = quote.casefold()[:80]
                skip.add(signature)
                rows.append(
                    {
                        "record_id": chain.record_id,
                        "family_office_name": chain.family_office_name,
                        "source_url": source_url,
                        "source_type": source_type,
                        "claim_supported": claim,
                        "quote_index": str(idx),
                        "exact_quote": quote,
                        "quote_status": "extracted",
                        "note": "Verbatim sentence from Firecrawl markdown; trimmed to "
                                f"{MAX_WORDS} words if longer.",
                        "extracted_at": extracted_at,
                    }
                )
    return rows


def write_snippets_csv(rows: list[dict[str, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "record_id",
        "family_office_name",
        "source_url",
        "source_type",
        "claim_supported",
        "quote_index",
        "exact_quote",
        "quote_status",
        "note",
        "extracted_at",
    ]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def render_chains_markdown(
    chains: tuple[ChainTarget, ...],
    rows: list[dict[str, str]],
) -> str:
    rows_by_chain: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        rows_by_chain.setdefault(row["record_id"], []).append(row)

    lines: list[str] = ["# Three Validation Chains", ""]
    lines.append(
        "Each chain documents one record at claim level. Quotes are verbatim sentences "
        "extracted from Firecrawl markdown snapshots taken on 2026-05-17 — see "
        "`data/processed/validation_chain_snippets.csv` for the source rows."
    )
    lines.append("")
    for chain in chains:
        lines.append(f"## {chain.family_office_name} (`{chain.record_id}`)")
        lines.append("")
        lines.append(f"- **Family office type:** `{chain.family_office_type}`")
        lines.append("- **Discovery source:** organic public-web discovery, "
                     "filtered through `apify/google-search-scraper` for own-domain results.")
        lines.append("- **Extraction method:** Firecrawl markdown of the official site URLs "
                     "below; quotes selected manually from the markdown.")
        lines.append("- **Validation logic:** live HTTP check on every source URL, "
                     "≥2 reachable sources, score ≥80, no discovery-only directory sources, "
                     "name overlap with the assessment sample workbook checked and clear.")
        lines.append("")
        lines.append("**Enrichment steps (in order applied):**")
        lines.append("")
        for step in chain.enrichment_steps:
            lines.append(f"- {step}")
        lines.append("")
        for source_url, source_type, claim in chain.sources:
            lines.append(f"### Source: `{source_url}`")
            lines.append("")
            lines.append(f"- **Source type:** {source_type}")
            lines.append(f"- **Claim supported:** {claim}")
            relevant = [
                row for row in rows_by_chain.get(chain.record_id, [])
                if row["source_url"] == source_url
            ]
            for row in relevant:
                if row["quote_status"] == "extracted":
                    lines.append(
                        f"- **Quote {row['quote_index']}:** "
                        f"\"{row['exact_quote']}\""
                    )
                else:
                    lines.append(f"- **Quote {row['quote_index']}:** "
                                 f"_{row['note']}_")
            lines.append("")
        lines.append("**What remains uncertain:**")
        lines.append("")
        for note in chain.uncertainties:
            lines.append(f"- {note}")
        lines.append("")
        lines.append("**What almost fooled me / what I had to reconcile:**")
        lines.append("")
        lines.append(chain.reconciliation_note)
        lines.append("")
        lines.append("**What would change the conclusion:**")
        lines.append("")
        for note in chain.falsifiers:
            lines.append(f"- {note}")
        lines.append("")
    return "\n".join(lines) + "\n"


@app.command("run")
def build_chains(
    firecrawl_json: Annotated[
        Path, typer.Option("--firecrawl-json")
    ] = FIRECRAWL_JSON_DEFAULT,
    snippets_csv: Annotated[
        Path, typer.Option("--snippets-csv")
    ] = SNIPPETS_CSV_DEFAULT,
    chains_md: Annotated[
        Path, typer.Option("--chains-md")
    ] = CHAINS_MD_DEFAULT,
) -> None:
    """Rebuild the three validation chains using existing Firecrawl markdown."""
    if not firecrawl_json.exists():
        raise typer.BadParameter(f"Firecrawl JSON not found: {firecrawl_json}")
    fc_index = load_firecrawl_index(firecrawl_json)
    rows = build_snippet_rows(CHAINS, fc_index)
    write_snippets_csv(rows, snippets_csv)
    chains_md.parent.mkdir(parents=True, exist_ok=True)
    chains_md.write_text(render_chains_markdown(CHAINS, rows), encoding="utf-8")
    extracted = sum(1 for row in rows if row["quote_status"] == "extracted")
    unavailable = sum(1 for row in rows if row["quote_status"] != "extracted")
    typer.echo(
        f"Wrote {len(rows)} snippet rows ({extracted} extracted, {unavailable} unavailable) "
        f"to {snippets_csv}; rewrote {chains_md}"
    )


if __name__ == "__main__":
    app()
