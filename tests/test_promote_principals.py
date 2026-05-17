from __future__ import annotations

from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from fo_dataset_pipeline.promote_principals import (
    ALL_SLOT_COLUMNS,
    CONFIDENCE_VALUE,
    app,
    build_updates,
    collapse_roster,
    role_rank,
)


def test_role_rank_orders_seniority() -> None:
    assert role_rank("Founder") == 1
    assert role_rank("Chief Executive Officer") < role_rank("Managing Partner")
    assert role_rank("Managing Partner") < role_rank("Partner")
    assert role_rank("Partner") < role_rank("Director")
    assert role_rank("Director") < role_rank("Senior Analyst")
    assert role_rank("") == 999
    assert role_rank("Random Role Word") == 999


def test_collapse_roster_groups_by_record_and_sorts_by_seniority() -> None:
    df = pd.DataFrame(
        [
            {"record_id": "fo_001", "principal_name": "Junior Lee",
             "principal_role": "Analyst", "source_url": "https://x.com/team"},
            {"record_id": "fo_001", "principal_name": "Senior Smith",
             "principal_role": "Managing Partner",
             "source_url": "https://x.com/team"},
            {"record_id": "fo_001", "principal_name": "Founder Bob",
             "principal_role": "Founder & CEO",
             "source_url": "https://x.com/team"},
            {"record_id": "fo_002", "principal_name": "Solo Doe",
             "principal_role": "Director", "source_url": "https://y.com/team"},
        ]
    )
    grouped = collapse_roster(df)
    assert list(grouped.keys()) == ["fo_001", "fo_002"]
    fo_001_names = [p["name"] for p in grouped["fo_001"]]
    assert fo_001_names == ["Founder Bob", "Senior Smith", "Junior Lee"]


def test_collapse_roster_skips_blank_names() -> None:
    df = pd.DataFrame(
        [
            {"record_id": "fo_001", "principal_name": "",
             "principal_role": "Director", "source_url": "x"},
            {"record_id": "fo_001", "principal_name": "Real Name",
             "principal_role": "Partner", "source_url": "x"},
        ]
    )
    grouped = collapse_roster(df)
    assert len(grouped["fo_001"]) == 1
    assert grouped["fo_001"][0]["name"] == "Real Name"


def test_build_updates_fills_up_to_three_slots() -> None:
    record = {}
    people = [
        {"name": "A", "role": "Founder", "source_url": "u1", "rank": 1},
        {"name": "B", "role": "Partner", "source_url": "u1", "rank": 7},
        {"name": "C", "role": "Director", "source_url": "u1", "rank": 11},
        {"name": "D", "role": "Analyst", "source_url": "u1", "rank": 15},
    ]
    updates = build_updates(record, people)
    assert updates["principal_1_name"] == "A"
    assert updates["principal_2_name"] == "B"
    assert updates["principal_3_name"] == "C"
    assert "principal_4_name" not in updates  # only 3 slots
    assert updates["principal_1_role"] == "Founder"
    assert updates["principal_1_confidence"] == CONFIDENCE_VALUE


def test_build_updates_preserves_existing_principal_slots() -> None:
    record = {"principal_1_name": "Existing Founder"}
    people = [
        {"name": "New Person", "role": "Founder", "source_url": "u", "rank": 1},
        {"name": "Other", "role": "Partner", "source_url": "u", "rank": 7},
    ]
    updates = build_updates(record, people)
    assert "principal_1_name" not in updates  # preserved
    assert updates["principal_2_name"] == "Other"


def test_build_updates_returns_empty_when_no_people() -> None:
    assert build_updates({}, []) == {}


def test_cli_run_promotion_writes_csv(tmp_path: Path) -> None:
    dataset = tmp_path / "validated.csv"
    pd.DataFrame(
        [
            {"record_id": "fo_001", "family_office_name": "Acme",
             "principal_1_name": ""},
            {"record_id": "fo_002", "family_office_name": "Other",
             "principal_1_name": ""},
        ]
    ).to_csv(dataset, index=False)
    roster = tmp_path / "roster.csv"
    pd.DataFrame(
        [
            {"record_id": "fo_001", "family_office_name": "Acme",
             "principal_name": "Jane Doe", "principal_role": "Founder",
             "source_url": "https://acme.com/team",
             "extraction_method": "test"},
            {"record_id": "fo_001", "family_office_name": "Acme",
             "principal_name": "John Roe", "principal_role": "Director",
             "source_url": "https://acme.com/team",
            "extraction_method": "test"},
        ]
    ).to_csv(roster, index=False)
    json_output = tmp_path / "out.json"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--dataset", str(dataset),
            "--roster", str(roster),
            "--json-output", str(json_output),
        ],
    )
    assert result.exit_code == 0, result.output

    df = pd.read_csv(dataset)
    fo_001 = df[df["record_id"] == "fo_001"].iloc[0]
    fo_002 = df[df["record_id"] == "fo_002"].iloc[0]
    assert fo_001["principal_1_name"] == "Jane Doe"
    assert fo_001["principal_2_name"] == "John Roe"
    assert pd.isna(fo_002["principal_1_name"]) or fo_002["principal_1_name"] == ""
    for column in ALL_SLOT_COLUMNS:
        assert column in df.columns
    assert json_output.exists()
