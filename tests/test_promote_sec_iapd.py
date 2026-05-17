from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from fo_dataset_pipeline.promote_sec_iapd import (
    CONFIDENCE_VALUE,
    EVIDENCE_COLUMN,
    PROMOTED_COLUMNS,
    UNCERTAINTY_SENTINEL,
    _append_uncertainty_note,
    app,
    build_updates,
)


def test_append_uncertainty_note_handles_empty_existing() -> None:
    assert _append_uncertainty_note("", "Note A") == "Note A"


def test_append_uncertainty_note_skips_duplicate() -> None:
    existing = "Already says Note A here"
    assert _append_uncertainty_note(existing, "Note A") == existing


def test_append_uncertainty_note_joins_with_period() -> None:
    assert _append_uncertainty_note("Older note", "New note") == "Older note. New note"


def test_build_updates_returns_empty_when_evidence_missing() -> None:
    assert build_updates({"record_id": "fo_x"}, None) == {}


def test_build_updates_promotes_registered_firm() -> None:
    record = {"record_id": "fo_001", "uncertainty_notes": ""}
    evidence = {
        "record_id": "fo_001",
        "family_office_name": "Acme",
        "sec_registered": True,
        "sec_crd_number": "151736",
        "sec_file_number": "801-70776",
        "sec_registration_status": "ACTIVE",
        "firm_name_iapd": "PATHSTONE",
        "firm_other_names": ["PATHSTONE FAMILY OFFICE, LLC"],
        "firm_branches_count": 162,
        "form_adv_brochure_url": (
            "https://reports.adviserinfo.sec.gov/reports/ADV/151736/PDF/151736.pdf"
        ),
        "sec_summary_url": "https://adviserinfo.sec.gov/firm/summary/151736",
        "sec_address": {
            "city": "ENGLEWOOD",
            "state": "NJ",
            "country": "United States",
        },
    }
    updates = build_updates(record, evidence)
    assert updates["sec_registered"] == "True"
    assert updates["sec_crd_number"] == "151736"
    assert updates["sec_file_number"] == "801-70776"
    assert updates["sec_registration_status"] == "ACTIVE"
    assert updates["sec_firm_name_iapd"] == "PATHSTONE"
    assert updates["sec_firm_other_names"] == "PATHSTONE FAMILY OFFICE, LLC"
    assert updates["sec_branches_count"] == "162"
    assert "151736" in updates["form_adv_brochure_url"]
    assert updates["sec_address_city"] == "ENGLEWOOD"
    assert updates[EVIDENCE_COLUMN].endswith("/151736")
    assert updates["sec_confidence"] == CONFIDENCE_VALUE


def test_build_updates_does_not_overwrite_existing_value_columns() -> None:
    record = {
        "record_id": "fo_001",
        "sec_crd_number": "EXISTING",
        "sec_firm_name_iapd": "EXISTING NAME",
    }
    evidence = {
        "record_id": "fo_001",
        "sec_registered": True,
        "sec_crd_number": "151736",
        "firm_name_iapd": "PATHSTONE",
        "sec_summary_url": "https://adviserinfo.sec.gov/firm/summary/151736",
    }
    updates = build_updates(record, evidence)
    # sec_registered IS allowed to write over since it's the gate column
    assert updates["sec_registered"] == "True"
    # ... but existing identifiers are preserved
    assert "sec_crd_number" not in updates
    assert "sec_firm_name_iapd" not in updates


def test_build_updates_marks_unregistered_firm_and_adds_uncertainty() -> None:
    record = {"record_id": "fo_002", "uncertainty_notes": ""}
    evidence = {
        "record_id": "fo_002",
        "family_office_name": "Tiny SFO",
        "sec_registered": False,
        "notes": "No IAPD match.",
    }
    updates = build_updates(record, evidence)
    assert updates["sec_registered"] == "False"
    assert UNCERTAINTY_SENTINEL in updates["uncertainty_notes"]


def test_build_updates_preserves_existing_uncertainty_when_unregistered() -> None:
    record = {
        "record_id": "fo_002",
        "uncertainty_notes": "Prior note about something else",
    }
    evidence = {"record_id": "fo_002", "sec_registered": False}
    updates = build_updates(record, evidence)
    assert updates["uncertainty_notes"].startswith("Prior note about something else")
    assert UNCERTAINTY_SENTINEL in updates["uncertainty_notes"]


def test_run_promotion_writes_csv_and_json(tmp_path: Path) -> None:
    dataset = tmp_path / "validated.csv"
    pd.DataFrame(
        [
            {"record_id": "fo_001", "family_office_name": "Acme",
             "uncertainty_notes": ""},
            {"record_id": "fo_002", "family_office_name": "Tiny",
             "uncertainty_notes": ""},
        ]
    ).to_csv(dataset, index=False)
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (evidence_dir / "fo_001.json").write_text(
        json.dumps(
            {
                "record_id": "fo_001",
                "sec_registered": True,
                "sec_crd_number": "151736",
                "sec_file_number": "801-70776",
                "sec_registration_status": "ACTIVE",
                "firm_name_iapd": "ACME WEALTH",
                "firm_other_names": [],
                "firm_branches_count": 3,
                "form_adv_brochure_url": "https://example.com/adv.pdf",
                "sec_summary_url": "https://adviserinfo.sec.gov/firm/summary/151736",
                "sec_address": {"city": "NYC", "state": "NY", "country": "US"},
            }
        ),
        encoding="utf-8",
    )
    (evidence_dir / "fo_002.json").write_text(
        json.dumps({"record_id": "fo_002", "sec_registered": False}),
        encoding="utf-8",
    )
    json_output = tmp_path / "out.json"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--dataset", str(dataset),
            "--evidence-dir", str(evidence_dir),
            "--json-output", str(json_output),
        ],
    )
    assert result.exit_code == 0, result.output

    df = pd.read_csv(dataset, dtype=str).fillna("")
    row_001 = df[df["record_id"] == "fo_001"].iloc[0]
    row_002 = df[df["record_id"] == "fo_002"].iloc[0]
    assert row_001["sec_registered"] == "True"
    assert row_001["sec_crd_number"] == "151736"
    assert row_002["sec_registered"] == "False"
    assert UNCERTAINTY_SENTINEL in row_002["uncertainty_notes"]
    for column in PROMOTED_COLUMNS:
        assert column in df.columns
