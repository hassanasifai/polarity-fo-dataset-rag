from pathlib import Path

from fo_dataset_pipeline.io import read_records, read_sample_workbook_names
from fo_dataset_pipeline.models import RawFamilyOfficeRecord
from fo_dataset_pipeline.validators import find_name_overlaps

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent


def test_raw_seed_dataset_has_50_valid_original_records() -> None:
    rows = read_records(PROJECT_ROOT / "data" / "raw" / "family_offices_seed.csv")
    records = [RawFamilyOfficeRecord.model_validate(row) for row in rows]
    sample_names = read_sample_workbook_names(
        WORKSPACE_ROOT / "assements_details" / "FO-MAX-data-sample-2.0.xlsx"
    )

    assert len(records) == 50
    assert len({record.record_id for record in records}) == 50
    assert not find_name_overlaps(
        [record.family_office_name for record in records],
        sample_names,
    )
    assert all(len(record.source_urls) >= 2 for record in records)
