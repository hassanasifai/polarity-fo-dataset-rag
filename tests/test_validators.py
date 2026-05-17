from fo_dataset_pipeline.validators import find_name_overlaps, normalize_entity_name


def test_normalize_entity_name_removes_common_suffixes() -> None:
    assert normalize_entity_name("Cascade Investments LLC") == "cascade investments"


def test_find_name_overlaps_catches_sample_equivalents() -> None:
    overlaps = find_name_overlaps(
        ["Cascade Investments LLC", "New Original Office"],
        {"Cascade Investments Llc"},
    )

    assert overlaps == ["Cascade Investments LLC"]
