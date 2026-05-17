"""Manual-review principal polish for the featured validation records.

The broad automated extractor only promotes principal slots when the existing
Firecrawl text has a clean name/role pattern. For the three featured validation
chains, I did a narrow official-site review and promoted only values that are
visible on the entity's own team/profile pages. Personal LinkedIn URLs remain
blank unless the official page links to the profile.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

app = typer.Typer(no_args_is_help=True)

DEFAULT_DATASET = Path("data/processed/family_offices_validated.csv")
DEFAULT_JSON_OUTPUT = Path("data/processed/family_offices_validated.json")


@dataclass(frozen=True)
class PrincipalSlot:
    name: str
    role: str
    source_url: str
    confidence: str = "official_team_page_manual_review"
    linkedin_url: str = ""
    linkedin_confidence: str = ""


SHOWCASE_PRINCIPALS: dict[str, tuple[PrincipalSlot, ...]] = {
    "fo_001": (
        PrincipalSlot("David Dekker", "Managing Partner", "https://www.cattrail.com/#Team"),
        PrincipalSlot("Russell Dekker", "Partner", "https://www.cattrail.com/#Team"),
        PrincipalSlot(
            "Andrew Budinoff",
            "Director of Portfolio Management and Trading",
            "https://www.cattrail.com/#Team",
        ),
    ),
    "fo_007": (
        PrincipalSlot(
            "Brandon C. Johnson, CFA",
            "Principal, Chief Executive Officer",
            "https://jfgfamilyoffice.com/bio/brandon-c-johnson,-cfa",
        ),
        PrincipalSlot(
            "Wendy M. Johnson, Esq.",
            "General Counsel",
            "https://jfgfamilyoffice.com/bio/wendy-m-johnson,-esq",
        ),
        PrincipalSlot(
            "Bert W. Williams",
            "Partner, Managing Director",
            "https://jfgfamilyoffice.com/bio/bert-w-williams",
        ),
    ),
    "fo_020": (
        PrincipalSlot(
            "Roberto Italia",
            "Chief Executive Officer",
            "https://www.verlinvest.com/team/roberto-italia/",
            linkedin_url="https://www.linkedin.com/in/roberto-italia-2244b82/",
            linkedin_confidence="linked_from_official_profile",
        ),
        PrincipalSlot(
            "Rachel Citera",
            "Principal, New York",
            "https://www.verlinvest.com/team/rachel-citera/",
            linkedin_url="https://www.linkedin.com/in/rachel-citera-a0a949160/",
            linkedin_confidence="linked_from_official_profile",
        ),
        PrincipalSlot(
            "William De Vliegher",
            "Principal - Operational Excellence, Brussels",
            "https://www.verlinvest.com/team/william-de-vliegher/",
            linkedin_url="https://www.linkedin.com/in/william-de-vliegher-59386a84/",
            linkedin_confidence="linked_from_official_profile",
        ),
    ),
}

NEW_COLUMNS = tuple(
    column
    for slot in (1, 2, 3)
    for column in (
        f"principal_{slot}_linkedin_url",
        f"principal_{slot}_linkedin_confidence",
    )
)


def promote_showcase_principals(df: pd.DataFrame) -> pd.DataFrame:
    output = df.copy()
    for column in NEW_COLUMNS:
        if column not in output.columns:
            output[column] = ""

    for index, row in output.iterrows():
        slots = SHOWCASE_PRINCIPALS.get(str(row.get("record_id") or ""))
        if not slots:
            continue
        for slot_number, slot in enumerate(slots, start=1):
            output.at[index, f"principal_{slot_number}_name"] = slot.name
            output.at[index, f"principal_{slot_number}_role"] = slot.role
            output.at[index, f"principal_{slot_number}_source_url"] = slot.source_url
            output.at[index, f"principal_{slot_number}_confidence"] = slot.confidence
            output.at[index, f"principal_{slot_number}_linkedin_url"] = slot.linkedin_url
            output.at[index, f"principal_{slot_number}_linkedin_confidence"] = (
                slot.linkedin_confidence
            )
    return output


@app.command("run")
def run_promote(
    dataset: Annotated[Path, typer.Option("--dataset")] = DEFAULT_DATASET,
    json_output: Annotated[Path, typer.Option("--json-output")] = DEFAULT_JSON_OUTPUT,
) -> None:
    """Promote official-site principal slots for the three featured records."""
    if not dataset.exists():
        raise typer.BadParameter(f"dataset not found: {dataset}")
    df = pd.read_csv(dataset, dtype=str).fillna("")
    output = promote_showcase_principals(df)
    output.to_csv(dataset, index=False)
    json_output.write_text(
        json.dumps(output.fillna("").to_dict(orient="records"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    touched = sorted(SHOWCASE_PRINCIPALS)
    typer.echo(f"Promoted official principal slots for {len(touched)} records: {touched}")


if __name__ == "__main__":
    app()
