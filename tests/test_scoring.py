from fo_dataset_pipeline.models import RawFamilyOfficeRecord, UrlCheck
from fo_dataset_pipeline.validators import score_record


def test_high_quality_record_scores_as_accepted() -> None:
    record = RawFamilyOfficeRecord.model_validate(
        {
            "record_id": "fo_test_004",
            "family_office_name": "Example Family Office",
            "family_office_type": "single_family_office",
            "description": "A real description for schema testing.",
            "investment_thesis": "Long-term private investments.",
            "investing_sectors": "Private equity; real estate",
            "website_url": "https://www.bessemertrust.com",
            "country": "United States",
            "principal_name": "Jane Doe",
            "principal_title": "Managing Director",
            "recent_activity": "Published a portfolio update.",
            "source_urls": (
                "https://www.bessemertrust.com/about; "
                "https://www.bessemertrust.com/services"
            ),
            "source_notes": "Schema test only.",
            "evidence_quality": "primary",
        }
    )

    score, confidence, notes, status = score_record(
        record,
        UrlCheck(url="https://www.bessemertrust.com", status_code=200, ok=True),
        [
            UrlCheck(url="https://www.bessemertrust.com/about", status_code=200, ok=True),
            UrlCheck(url="https://www.bessemertrust.com/services", status_code=200, ok=True),
        ],
    )

    assert score >= 70
    assert confidence in {"medium", "high"}
    assert status == "accepted"
    assert "passed" in notes


def test_discovery_only_directory_source_blocks_acceptance() -> None:
    record = RawFamilyOfficeRecord.model_validate(
        {
            "record_id": "fo_test_007",
            "family_office_name": "Directory Backed Office",
            "family_office_type": "single_family_office",
            "description": "A real description for schema testing.",
            "investment_thesis": "Long-term private investments.",
            "investing_sectors": "Private equity; real estate",
            "website_url": "https://www.bessemertrust.com",
            "country": "United States",
            "source_urls": (
                "https://www.bessemertrust.com/bessemer-experience/"
                "deep-family-office-expertise; "
                "https://dev.swfinstitute.org/fund-rankings/family-office"
            ),
            "source_notes": "Schema test only.",
            "evidence_quality": "primary",
        }
    )

    _score, _confidence, notes, status = score_record(
        record,
        UrlCheck(url="https://www.bessemertrust.com", status_code=200, ok=True),
        [
            UrlCheck(
                url=(
                    "https://www.bessemertrust.com/bessemer-experience/"
                    "deep-family-office-expertise"
                ),
                status_code=200,
                ok=True,
            ),
            UrlCheck(
                url="https://dev.swfinstitute.org/fund-rankings/family-office",
                status_code=200,
                ok=True,
            ),
        ],
    )

    assert status == "needs_review"
    assert "discovery-only" in notes
