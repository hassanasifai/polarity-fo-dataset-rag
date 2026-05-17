from __future__ import annotations

from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from fo_dataset_pipeline.apply_audit import (
    AUDIT_DECISIONS,
    app,
    apply_decisions,
)


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows).fillna("")


def test_apply_decisions_sets_explicit_verdict() -> None:
    df = _frame([
        {"record_id": "fo_test", "uncertainty_notes": "existing", "human_audit_status": "pending"},
    ])
    decisions = {"fo_test": {"verdict": "relabel", "note_addendum": ""}}
    out, explicit, default = apply_decisions(df, decisions)
    assert out.loc[0, "human_audit_status"] == "relabel"
    assert explicit == 1
    assert default == 0


def test_apply_decisions_appends_note_addendum_when_present() -> None:
    df = _frame([
        {"record_id": "fo_test", "uncertainty_notes": "existing note",
         "human_audit_status": "pending"},
    ])
    decisions = {"fo_test": {"verdict": "pass", "note_addendum": "extra context"}}
    out, _, _ = apply_decisions(df, decisions)
    assert "existing note" in out.loc[0, "uncertainty_notes"]
    assert "extra context" in out.loc[0, "uncertainty_notes"]


def test_apply_decisions_is_idempotent() -> None:
    df = _frame([
        {"record_id": "fo_test", "uncertainty_notes": "",
         "human_audit_status": "pending"},
    ])
    decisions = {"fo_test": {"verdict": "pass", "note_addendum": "brand note"}}
    once, _, _ = apply_decisions(df, decisions)
    twice, _, _ = apply_decisions(once, decisions)
    # Note should appear exactly once
    assert twice.loc[0, "uncertainty_notes"].count("brand note") == 1


def test_apply_decisions_defaults_unmatched_rows() -> None:
    df = _frame([
        {"record_id": "fo_001", "uncertainty_notes": "", "human_audit_status": "pending"},
        {"record_id": "fo_002", "uncertainty_notes": "", "human_audit_status": "pending"},
    ])
    decisions = {"fo_001": {"verdict": "weak", "note_addendum": ""}}
    out, explicit, default = apply_decisions(df, decisions, default_verdict="pass")
    assert out.loc[0, "human_audit_status"] == "weak"
    assert out.loc[1, "human_audit_status"] == "pass"
    assert explicit == 1
    assert default == 1


def test_apply_decisions_creates_status_column_when_missing() -> None:
    df = _frame([
        {"record_id": "fo_test", "uncertainty_notes": ""},
    ])
    out, _, _ = apply_decisions(df, {})
    assert "human_audit_status" in out.columns
    assert out.loc[0, "human_audit_status"] == "pass"


def test_audit_decisions_targets_all_pre_screen_flags() -> None:
    expected_record_ids = {
        "fo_004", "fo_005", "fo_011", "fo_022", "fo_024",
        "fo_026", "fo_040", "fo_042", "fo_049",
    }
    assert set(AUDIT_DECISIONS.keys()) == expected_record_ids
    for record_id, decision in AUDIT_DECISIONS.items():
        assert decision["verdict"] in {"pass", "relabel", "weak"}, record_id


def test_cli_run_apply_updates_csv(tmp_path: Path) -> None:
    dataset = tmp_path / "validated.csv"
    pd.DataFrame(
        [
            {"record_id": "fo_004", "uncertainty_notes": "",
             "human_audit_status": "pending"},
            {"record_id": "fo_xxx", "uncertainty_notes": "",
             "human_audit_status": "pending"},
        ]
    ).to_csv(dataset, index=False)

    runner = CliRunner()
    result = runner.invoke(app, ["--dataset", str(dataset)])
    assert result.exit_code == 0, result.output

    df = pd.read_csv(dataset)
    statuses = dict(zip(df["record_id"], df["human_audit_status"], strict=True))
    assert statuses["fo_004"] == "pass"  # explicit
    assert statuses["fo_xxx"] == "pass"  # default


def test_cli_rejects_invalid_default_verdict(tmp_path: Path) -> None:
    dataset = tmp_path / "validated.csv"
    pd.DataFrame([{"record_id": "fo_001"}]).to_csv(dataset, index=False)
    runner = CliRunner()
    result = runner.invoke(
        app, ["--dataset", str(dataset), "--default-verdict", "invalid"]
    )
    assert result.exit_code != 0
