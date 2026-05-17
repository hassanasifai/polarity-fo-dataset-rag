import pytest
from pydantic import ValidationError

from fo_dataset_pipeline.models import RawFamilyOfficeRecord


def test_source_urls_split_from_semicolon_string() -> None:
    record = RawFamilyOfficeRecord.model_validate(
        {
            "record_id": "fo_test_001",
            "family_office_name": "Example Family Office",
            "family_office_type": "single_family_office",
            "description": "A real description for schema testing.",
            "website_url": "https://www.bessemertrust.com",
            "country": "United States",
            "source_urls": (
                "https://www.bessemertrust.com/about; "
                "https://www.bessemertrust.com/services"
            ),
            "source_notes": "Schema test only.",
            "evidence_quality": "primary",
        }
    )

    assert len(record.source_urls) == 2


def test_requires_two_source_urls() -> None:
    with pytest.raises(ValidationError, match="at least two source URLs"):
        RawFamilyOfficeRecord.model_validate(
            {
                "record_id": "fo_test_002",
                "family_office_name": "One Source Office",
                "family_office_type": "single_family_office",
                "description": "A real description for schema testing.",
                "website_url": "https://www.bessemertrust.com",
                "country": "United States",
                "source_urls": "https://www.bessemertrust.com/about",
                "source_notes": "Schema test only.",
                "evidence_quality": "primary",
            }
        )


def test_rejects_placeholder_values_and_domains() -> None:
    with pytest.raises(ValidationError, match="placeholder"):
        RawFamilyOfficeRecord.model_validate(
            {
                "record_id": "fo_test_003",
                "family_office_name": "Placeholder Office",
                "family_office_type": "single_family_office",
                "description": "Hidden",
                "website_url": "https://example.com",
                "country": "United States",
                "source_urls": "https://example.com/about; https://example.com/team",
                "source_notes": "Schema test only.",
                "evidence_quality": "primary",
            }
        )
