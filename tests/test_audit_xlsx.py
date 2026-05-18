from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = PROJECT_ROOT / "scripts" / "audit_xlsx.py"

spec = importlib.util.spec_from_file_location("audit_xlsx", AUDIT_PATH)
assert spec is not None
assert spec.loader is not None
audit_xlsx = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = audit_xlsx
spec.loader.exec_module(audit_xlsx)


def test_parse_source_urls_prefers_json_and_warns_legacy_formats() -> None:
    parsed_json = audit_xlsx.parse_source_urls_cell(
        '["https://example.com/a", "https://example.com/b"]'
    )
    parsed_legacy = audit_xlsx.parse_source_urls_cell(
        "['https://example.com/a', 'https://example.com/b']"
    )
    parsed_invalid = audit_xlsx.parse_source_urls_cell("{not json")

    assert parsed_json.format_name == "json_array"
    assert parsed_json.urls == ["https://example.com/a", "https://example.com/b"]
    assert parsed_legacy.format_name == "legacy_python_list"
    assert parsed_invalid.format_name == "invalid"
    assert parsed_invalid.error


def test_check_unique_ids_flags_duplicate_claim_ids() -> None:
    result = audit_xlsx.AuditResult()
    df = pd.DataFrame(
        {
            "claim_id": ["fo_001_name", "fo_001_name", "fo_002_name"],
            "record_id": ["fo_001", "fo_001", "fo_002"],
        }
    )

    audit_xlsx.check_unique_ids(df, "field_evidence", "claim_id", result)

    assert result.issues == ["Duplicate field_evidence.claim_id values: ['fo_001_name']"]


def test_source_reference_registry_allows_registry_and_existing_local_artifacts(
    tmp_path: Path,
) -> None:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "methodology_summary.md").write_text("ok", encoding="utf-8")
    registry_urls = {audit_xlsx.normalize_url("https://example.com/source")}
    refs = pd.DataFrame(
        {
            "record_id": ["fo_001", "fo_002", "fo_003"],
            "claim_id": ["claim_1", "claim_2", "claim_3"],
            "source_url": [
                "https://example.com/source/",
                "reports/methodology_summary.md",
                "https://missing.example/source",
            ],
        }
    )

    missing = audit_xlsx.find_unregistered_source_references(
        "field_evidence",
        refs,
        "source_url",
        registry_urls,
        tmp_path,
    )

    assert len(missing) == 1
    assert missing[0].record_id == "fo_003"
    assert missing[0].value == "https://missing.example/source"


def test_venitage_mismatch_detects_gjelina_content() -> None:
    rows = pd.DataFrame(
        {
            "record_id": ["fo_009", "fo_010"],
            "source_id": ["fo_009_src_01", "fo_010_src_01"],
            "source_url": ["https://venitage.com/", "https://example.com/"],
            "evidence_snippet": [
                "# Gjelina: California Cool in Venice Beach",
                "Correct evidence",
            ],
        }
    )

    mismatches = audit_xlsx.find_suspicious_venitage_rows(rows)

    assert mismatches == [
        "row 2: fo_009_src_01 https://venitage.com/ contains Gjelina/Venice Beach text"
    ]


def test_sec_near_matches_require_documented_review_status(tmp_path: Path) -> None:
    sec_dir = tmp_path / "sec"
    sec_dir.mkdir()
    (sec_dir / "fo_bad.json").write_text(
        json.dumps(
            {
                "record_id": "fo_bad",
                "family_office_name": "Near Miss",
                "match_score": 0.55,
                "match_threshold": 0.6,
                "match_reason": "name_jaccard=0.55",
            }
        ),
        encoding="utf-8",
    )
    (sec_dir / "fo_ok.json").write_text(
        json.dumps(
            {
                "record_id": "fo_ok",
                "family_office_name": "Reviewed Near Miss",
                "match_score": 0.55,
                "match_threshold": 0.6,
                "match_reason": "name_jaccard=0.55",
                "review_status": "false_positive",
            }
        ),
        encoding="utf-8",
    )

    missing = audit_xlsx.find_sec_near_matches_without_review(sec_dir)

    assert [item.record_id for item in missing] == ["fo_bad"]


def test_stale_public_recency_wording_is_detected(tmp_path: Path) -> None:
    doc = tmp_path / "assessment_notes.md"
    doc.write_text("No recent public signal as of 2026-05-17.", encoding="utf-8")
    data = pd.DataFrame(
        {
            "record_id": ["fo_001"],
            "uncertainty_notes": ["no recent public signal as of 2026-05-17"],
        }
    )

    stale = audit_xlsx.find_stale_public_recency_wording(
        data=data,
        doc_paths=[doc],
        audit_date=date(2026, 5, 18),
    )

    assert stale == [
        "data_50.uncertainty_notes fo_001: no recent public signal as of 2026-05-17",
        f"{doc.as_posix()}: No recent public signal as of 2026-05-17",
    ]
