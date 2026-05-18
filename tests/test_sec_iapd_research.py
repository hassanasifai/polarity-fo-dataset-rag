from __future__ import annotations

from fo_dataset_pipeline.sec_iapd_research import _score_hit


def test_score_hit_accepts_simplified_name_match() -> None:
    score, reason = _score_hit(
        {
            "firm_name": "VENITAGE, LLC",
            "firm_other_names": ["VENITAGE, LLC"],
            "firm_ia_address_details": '{"officeAddress": {"city": "EDEN PRAIRIE", "state": "MN"}}',
        },
        {
            "family_office_name": "Venitage",
            "city": "Eden Prairie",
            "state_region": "MN",
        },
    )

    assert score >= 0.75
    assert "simplified_name_exact_match" in reason


def test_score_hit_keeps_weak_name_match_below_threshold_without_address() -> None:
    score, reason = _score_hit(
        {
            "firm_name": "UNRELATED ADVISORS",
            "firm_other_names": [],
            "firm_ia_address_details": '{"officeAddress": {"city": "MIAMI", "state": "FL"}}',
        },
        {
            "family_office_name": "Venitage",
            "city": "Eden Prairie",
            "state_region": "MN",
        },
    )

    assert score < 0.6
    assert "name_jaccard" in reason
