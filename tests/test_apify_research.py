from pathlib import Path

from fo_dataset_pipeline.apify_research import (
    actor_path,
    canonical_url,
    evidence_snippet,
    flatten_serp_items,
    google_search_input,
    source_urls_from_dataset,
    triage_serp_result,
    website_crawler_input,
)


def test_actor_path_uses_apify_api_actor_id_format() -> None:
    assert actor_path("apify/google-search-scraper") == "apify~google-search-scraper"


def test_google_search_input_disables_costly_addons() -> None:
    payload = google_search_input(["family office"], "us")

    assert payload["maxPagesPerQuery"] == 1
    assert payload["maximumLeadsEnrichmentRecords"] == 0
    assert payload["focusOnPaidAds"] is False


def test_website_crawler_input_is_depth_zero_and_bounded() -> None:
    payload = website_crawler_input(["https://example.org/about", "https://example.org/team"])

    assert payload["maxCrawlDepth"] == 0
    assert payload["maxCrawlPages"] == 2
    assert payload["maxResults"] == 2
    assert payload["respectRobotsTxtFile"] is True
    assert payload["blockMedia"] is True


def test_source_urls_from_dataset_removes_pdfs_and_dedupes(tmp_path: Path) -> None:
    path = tmp_path / "records.csv"
    path.write_text(
        "source_urls\n"
        "\"https://example.org/about; https://example.org/about; "
        "https://example.org/disclosure.pdf\"\n",
        encoding="utf-8",
    )

    assert source_urls_from_dataset(path) == ["https://example.org/about"]


def test_canonical_url_strips_fragment_and_trailing_slash() -> None:
    assert canonical_url("https://example.org/about/#team") == "https://example.org/about"


def test_evidence_snippet_prefers_family_office_sentence() -> None:
    snippet = evidence_snippet(
        "Intro text. The firm is a multi-family office serving client families. More text."
    )

    assert "multi-family office" in snippet


def test_triage_serp_result_rejects_social_directory_domains() -> None:
    status, reason = triage_serp_result(
        "Example Family Office",
        "Family office profile",
        "https://www.linkedin.com/company/example",
    )

    assert status == "reject"
    assert "directory" in reason


def test_flatten_serp_items_extracts_nested_organic_results() -> None:
    rows = flatten_serp_items(
        [
            {
                "searchQuery": {"term": "family office"},
                "organicResults": [
                    {
                        "position": 1,
                        "title": "Example Family Office",
                        "url": "https://examplefo.com/",
                        "description": "Official multi-family office.",
                    }
                ],
            }
        ]
    )

    assert rows[0]["query"] == "family office"
    assert rows[0]["triage_status"] == "candidate_raw"
