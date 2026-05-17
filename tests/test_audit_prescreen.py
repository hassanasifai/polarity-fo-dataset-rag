from __future__ import annotations

from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from fo_dataset_pipeline.audit_prescreen import (
    HEURISTICS,
    app,
    prescreen_row,
    write_worksheet,
)


def _row(**overrides: object) -> dict:
    base = {
        "record_id": "fo_test",
        "family_office_name": "Acme Family Office",
        "family_office_type": "multi_family_office",
        "description": "Test description with substance and family office context.",
        "website_url": "https://acme.com/",
        "principal_name": "",
        "uncertainty_notes": "",
    }
    base.update(overrides)
    return base


def test_h1_fires_for_sfo_without_specific_principal() -> None:
    row = _row(family_office_type="single_family_office", principal_name="")
    flag, reason = prescreen_row(row)
    assert flag == "look_carefully"
    assert "H1_sfo_no_specific_principal" in reason


def test_h1_fires_for_sfo_with_only_generic_family_token() -> None:
    row = _row(family_office_type="single_family_office", principal_name="family")
    flag, reason = prescreen_row(row)
    assert "H1_sfo_no_specific_principal" in reason


def test_h1_silent_for_sfo_with_specific_principal() -> None:
    row = _row(
        family_office_type="single_family_office",
        principal_name="Dekker family",
        website_url="https://dekker.com/",
    )
    flag, reason = prescreen_row(row)
    assert "H1_sfo_no_specific_principal" not in reason


def test_h8_fires_for_service_provider_mfo() -> None:
    row = _row(uncertainty_notes="Accepted as service-provider MFO not a private SFO")
    flag, reason = prescreen_row(row)
    assert "H8_service_provider_mfo" in reason


def test_h5_silent_when_domain_contains_name_token() -> None:
    row = _row(family_office_name="Cat Trail Capital", website_url="https://cattrail.com/")
    flag, reason = prescreen_row(row)
    assert "H5_domain_name_mismatch" not in reason


def test_h5_fires_for_abbreviated_domain() -> None:
    row = _row(family_office_name="Homrich Berg", website_url="https://hbwealth.com/")
    flag, reason = prescreen_row(row)
    assert "H5_domain_name_mismatch" in reason


def test_clean_row_passes_all_heuristics() -> None:
    row = _row(
        family_office_name="Cat Trail Capital",
        website_url="https://cattrail.com/",
        family_office_type="single_family_office",
        principal_name="Dekker family",
        uncertainty_notes="High-confidence SFO from entity website",
    )
    flag, reason = prescreen_row(row)
    assert flag == "looks_clean"
    assert reason == ""


def test_all_heuristics_registered() -> None:
    codes = {code for code, _ in HEURISTICS}
    assert codes == {
        "H1_sfo_no_specific_principal",
        "H8_service_provider_mfo",
        "H5_domain_name_mismatch",
    }


def test_run_prescreen_writes_columns_and_worksheet(tmp_path: Path) -> None:
    dataset = tmp_path / "validated.csv"
    pd.DataFrame(
        [
            _row(record_id="fo_001", family_office_name="Cat Trail",
                 website_url="https://cattrail.com/"),
            _row(record_id="fo_002", family_office_name="Homrich Berg",
                 website_url="https://hbwealth.com/"),
        ]
    ).to_csv(dataset, index=False)
    worksheet = tmp_path / "reports" / "manual_audit_worksheet.md"

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["--dataset", str(dataset), "--worksheet", str(worksheet)],
    )
    assert result.exit_code == 0, result.output

    df = pd.read_csv(dataset)
    assert {"human_audit_status", "auto_prescreen_flag", "auto_prescreen_reason"} <= set(df.columns)
    assert (df["human_audit_status"] == "pending").all()
    assert worksheet.exists()
    body = worksheet.read_text(encoding="utf-8")
    assert "Pre-screen summary" in body
    assert "fo_001" in body


def test_write_worksheet_preserves_existing_human_status(tmp_path: Path) -> None:
    dataset = tmp_path / "validated.csv"
    pd.DataFrame(
        [
            _row(record_id="fo_001"),
            _row(record_id="fo_002"),
        ]
    ).assign(human_audit_status=["pass", ""]).to_csv(dataset, index=False)
    worksheet = tmp_path / "manual_audit_worksheet.md"

    runner = CliRunner()
    runner.invoke(app, ["--dataset", str(dataset), "--worksheet", str(worksheet)])

    df = pd.read_csv(dataset)
    statuses = dict(zip(df["record_id"], df["human_audit_status"], strict=True))
    assert statuses["fo_001"] == "pass"
    assert statuses["fo_002"] == "pending"


def test_write_worksheet_handles_no_flagged_rows(tmp_path: Path) -> None:
    df = pd.DataFrame(
        [
            _row(
                record_id="fo_001",
                family_office_name="Cat Trail",
                website_url="https://cattrail.com/",
                auto_prescreen_flag="looks_clean",
                auto_prescreen_reason="",
            )
        ]
    )
    output = tmp_path / "worksheet.md"
    write_worksheet(df, output)
    body = output.read_text(encoding="utf-8")
    assert "Flagged rows" not in body
    assert "fo_001" in body
