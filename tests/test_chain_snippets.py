from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from fo_dataset_pipeline.chain_snippets import (
    CHAINS,
    _clean_markdown,
    app,
    build_snippet_rows,
    extract_quotes,
    load_firecrawl_index,
)


def test_clean_markdown_strips_image_and_link_noise() -> None:
    raw = "![alt](https://x.com/i.png) [About](https://x.com/about) ## Heading text - nav"
    cleaned = _clean_markdown(raw)
    assert "![" not in cleaned
    assert "About" in cleaned
    assert "Heading" in cleaned


def test_extract_quotes_picks_primary_keyword_sentence() -> None:
    md = (
        "## What We Do\n"
        "Cat Trail is a single family office serving the Dekker family.\n"
        "Random navigation list item.\n"
        "Wealth planning is also offered."
    )
    quotes = extract_quotes(md, max_quotes=2)
    assert any("single family office" in q for q in quotes)


def test_extract_quotes_returns_empty_when_no_keyword_match() -> None:
    md = "Roberto Italia. Arjun Anand. Thibault Biebuyck."
    assert extract_quotes(md) == []


def test_extract_quotes_trims_long_sentences_to_max_words() -> None:
    long_sentence = (
        "We are a family office that " + " ".join(f"token{i}" for i in range(50)) + "."
    )
    quotes = extract_quotes(long_sentence, max_quotes=1)
    assert len(quotes) == 1
    assert quotes[0].endswith("…")
    # 25 tokens + ellipsis
    assert quotes[0].count(" ") <= 25


def test_extract_quotes_skips_signatures() -> None:
    md = "Cat Trail is a single family office serving the Dekker family. " * 2
    md = md + " Cat Trail serves multigenerational planning needs."
    first = extract_quotes(md, max_quotes=1)
    assert first
    skip = {first[0].casefold()[:80]}
    second = extract_quotes(md, max_quotes=1, skip_signatures=skip)
    assert second
    assert second[0] != first[0]


def test_load_firecrawl_index_keeps_longest_markdown(tmp_path: Path) -> None:
    path = tmp_path / "fc.json"
    payload = {
        "data": [
            {"metadata": {"sourceURL": "https://x.com/"}, "markdown": "short"},
            {"metadata": {"sourceURL": "https://x.com/"}, "markdown": "this is the longer one"},
            {"metadata": {"sourceURL": "https://y.com/"}, "markdown": "y"},
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    index = load_firecrawl_index(path)
    assert index["https://x.com/"] == "this is the longer one"
    assert index["https://y.com/"] == "y"


def test_build_snippet_rows_records_unavailable_for_missing_url() -> None:
    rows = build_snippet_rows(CHAINS, fc_index={})
    statuses = {row["quote_status"] for row in rows}
    assert "markdown_unavailable" in statuses


def test_build_snippet_rows_uses_per_chain_signature_dedup() -> None:
    repeating = (
        "Cat Trail is a single family office serving the Dekker family. "
        "Investment management is the primary focus."
    )
    fc_index = {
        "https://www.cattrail.com/": repeating,
        "https://www.cattrail.com/#About": repeating,
        "https://www.cattrail.com/#Team": repeating,
    }
    rows = build_snippet_rows(CHAINS[:1], fc_index=fc_index)
    extracted_quotes = [r["exact_quote"] for r in rows if r["quote_status"] == "extracted"]
    # signatures must not duplicate across the 3 anchor URLs sharing markdown
    assert len(extracted_quotes) == len(set(extracted_quotes))


def test_cli_run_writes_outputs(tmp_path: Path) -> None:
    fc_path = tmp_path / "fc.json"
    fc_path.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "metadata": {"sourceURL": "https://www.cattrail.com/"},
                        "markdown": (
                            "Cat Trail is a single family office serving the Dekker family. "
                            "It manages family capital through investment partners."
                        ),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    snippets_csv = tmp_path / "snippets.csv"
    chains_md = tmp_path / "chains.md"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--firecrawl-json", str(fc_path),
            "--snippets-csv", str(snippets_csv),
            "--chains-md", str(chains_md),
        ],
    )
    assert result.exit_code == 0, result.output
    assert snippets_csv.exists()
    body = chains_md.read_text(encoding="utf-8")
    assert "Cat Trail Capital" in body
    assert "single family office" in body
