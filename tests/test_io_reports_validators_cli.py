from pathlib import Path

from typer.testing import CliRunner

from fo_dataset_pipeline.cli import app
from fo_dataset_pipeline.io import read_records, read_sample_workbook_names, write_outputs
from fo_dataset_pipeline.models import RawFamilyOfficeRecord, UrlCheck, ValidatedFamilyOfficeRecord
from fo_dataset_pipeline.reports import (
    build_validation_chains,
    build_validation_report,
    write_reports,
)
from fo_dataset_pipeline.validators import check_url, domain_from_url, has_dns, score_record


def make_record(**overrides: object) -> RawFamilyOfficeRecord:
    data: dict[str, object] = {
        "record_id": "fo_test_005",
        "family_office_name": "Bessemer Trust",
        "family_office_type": "multi_family_office",
        "description": "A family office services firm.",
        "investment_thesis": "Long-term diversified investment management.",
        "investing_sectors": "Private equity; real estate",
        "website_url": "https://www.bessemertrust.com",
        "country": "United States",
        "principal_name": "Jane Doe",
        "principal_title": "Managing Director",
        "recent_activity": "Published an update.",
        "source_urls": (
            "https://www.bessemertrust.com/about; "
            "https://www.bessemertrust.com/services"
        ),
        "source_notes": "Official website pages.",
        "evidence_quality": "primary",
    }
    data.update(overrides)
    return RawFamilyOfficeRecord.model_validate(data)


def make_validated(status: str = "accepted") -> ValidatedFamilyOfficeRecord:
    record = make_record()
    return ValidatedFamilyOfficeRecord(
        **record.model_dump(),
        website_check=UrlCheck(url="https://www.bessemertrust.com", status_code=200, ok=True),
        source_checks=[
            UrlCheck(url="https://www.bessemertrust.com/about", status_code=200, ok=True),
            UrlCheck(url="https://www.bessemertrust.com/services", status_code=200, ok=True),
        ],
        source_count=2,
        validation_score=88,
        confidence="high",
        validation_status=status,
        validation_notes="passed configured validation checks",
    )


def test_read_and_write_outputs(tmp_path: Path) -> None:
    input_path = tmp_path / "input.csv"
    input_path.write_text(
        "family_office_name,website_url,source_urls\n"
        "Bessemer,https://www.bessemertrust.com,https://www.bessemertrust.com/about\n",
        encoding="utf-8",
    )

    rows = read_records(input_path)
    write_outputs(rows, tmp_path / "out")

    assert rows[0]["family_office_name"] == "Bessemer"
    assert (tmp_path / "out" / "family_offices_validated.csv").exists()
    assert (tmp_path / "out" / "family_offices_validated.xlsx").exists()
    assert (tmp_path / "out" / "family_offices_validated.json").exists()


def test_reports_include_review_and_chain_details() -> None:
    accepted = make_validated()
    needs_review = make_validated(status="needs_review")
    needs_review.validation_score = 61
    needs_review.confidence = "medium"

    report = build_validation_report([accepted, needs_review])
    chains = build_validation_chains([accepted], limit=1)

    assert "Needs review: 1" in report
    assert "Bessemer Trust" in chains
    assert "Exact sources" in chains


def test_write_reports_and_missing_sample_workbook(tmp_path: Path) -> None:
    write_reports([make_validated()], tmp_path)

    assert (tmp_path / "validation_report.md").exists()
    assert (tmp_path / "validation_chains.md").exists()
    assert read_sample_workbook_names(tmp_path / "missing.xlsx") == set()


def test_domain_and_dns_helpers() -> None:
    assert domain_from_url("https://www.example.com/path") == "example.com"
    assert has_dns("example.com") is True
    assert has_dns("invalid.invalid") is False


def test_low_score_record_needs_review() -> None:
    record = make_record(
        family_office_type="unclear",
        investment_thesis="",
        investing_sectors="",
        website_url="https://does-not-resolve.invalid",
        source_urls=(
            "https://does-not-resolve.invalid/about; "
            "https://does-not-resolve.invalid/team"
        ),
        evidence_quality="unverified",
        principal_name="",
        principal_title="",
        recent_activity="",
    )

    score, confidence, notes, status = score_record(
        record,
        UrlCheck(url="https://does-not-resolve.invalid", ok=False),
        [
            UrlCheck(url="https://does-not-resolve.invalid/about", ok=False),
            UrlCheck(url="https://does-not-resolve.invalid/team", ok=False),
        ],
    )

    assert score < 70
    assert confidence == "low"
    assert status == "needs_review"
    assert "evidence quality is unverified" in notes


def test_cli_validate_with_patched_validator(tmp_path: Path, monkeypatch) -> None:
    input_path = tmp_path / "records.csv"
    input_path.write_text(
        "record_id,family_office_name,family_office_type,description,website_url,country,"
        "source_urls,source_notes,evidence_quality\n"
        "fo_test_006,Bessemer Trust,multi_family_office,A family office services firm.,"
        "https://www.bessemertrust.com,United States,"
        "https://www.bessemertrust.com/about; https://www.bessemertrust.com/services,"
        "Official pages,primary\n",
        encoding="utf-8",
    )

    async def fake_validate_records(records: list[RawFamilyOfficeRecord]):
        return [make_validated()]

    monkeypatch.setattr("fo_dataset_pipeline.cli.validate_records", fake_validate_records)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--input",
            str(input_path),
            "--output-dir",
            str(tmp_path / "processed"),
            "--report-dir",
            str(tmp_path / "reports"),
        ],
    )

    assert result.exit_code == 0
    assert "Processed 1 records; accepted 1" in result.output
    assert (tmp_path / "reports" / "validation_report.md").exists()


def test_check_url_handles_http_errors() -> None:
    class HttpxFailingClient:
        async def get(self, url: str, follow_redirects: bool):
            import httpx

            raise httpx.ConnectError("boom")

    import asyncio

    result = asyncio.run(check_url(HttpxFailingClient(), "https://example.test"))

    assert result.ok is False
    assert result.error == "boom"
