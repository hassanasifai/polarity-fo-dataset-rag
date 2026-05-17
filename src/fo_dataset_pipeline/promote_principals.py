"""Promote multi-principal columns from team_rosters_raw.csv.

The team roster extractor produces one row per (FO, person) pair from
Firecrawl-captured team pages. This module collapses those rows into up to
three principal columns per FO (``principal_1_*``, ``principal_2_*``,
``principal_3_*``), ordered by role seniority. Existing ``principal_name`` /
``principal_title`` columns on the validated CSV are preserved — the new
columns are additive.

Confidence labels:
- ``corporate_team_page`` — name + role observed on the FO's own team / about
  page (the source we have).

Email and LinkedIn URLs are NOT inferred here — the team-page evidence does not
include them. Those fields stay null with explicit honest-blank notes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

app = typer.Typer(no_args_is_help=True)

DEFAULT_DATASET = Path("data/processed/family_offices_validated.csv")
DEFAULT_ROSTER = Path("data/processed/team_rosters_raw.csv")
DEFAULT_JSON_OUTPUT = Path("data/processed/family_offices_validated.json")

# Seniority ranking — lower index = more senior. Used to order principals
# within a single FO.
ROLE_RANK_PATTERNS: tuple[tuple[str, int], ...] = (
    (r"\b(?:founder|co[-\s]?founder|cofounder)\b", 1),
    (r"\b(?:chair(?:man|person)?|chair)\b", 2),
    (r"\bpresident\b", 3),
    (r"\bchief\s+(?:executive|investment|financial|operating|technology|of\s+staff)\b", 4),
    (r"\b(?:ceo|cio|cfo|coo|cto)\b", 4),
    (r"\bmanaging\s+(?:partner|director)\b", 5),
    (r"\b(?:senior\s+partner)\b", 6),
    (r"\b(?:partner)\b", 7),
    (r"\bprincipal\b", 8),
    (r"\b(?:executive|senior)\s+director\b", 9),
    (r"\bvice\s+president\b", 10),
    (r"\bdirector\b", 11),
    (r"\bhead\s+of\b", 12),
    (r"\btrustee\b", 13),
    (r"\b(?:senior\s+advisor)\b", 14),
    (r"\b(?:senior|executive|associate|analyst|manager|lead)\b", 15),
)

PRINCIPAL_SLOTS = (1, 2, 3)
CONFIDENCE_VALUE = "corporate_team_page"
SLOT_COLUMN_TEMPLATE = (
    "principal_{slot}_name",
    "principal_{slot}_role",
    "principal_{slot}_source_url",
    "principal_{slot}_confidence",
)
ALL_SLOT_COLUMNS = tuple(
    template.format(slot=slot)
    for slot in PRINCIPAL_SLOTS
    for template in SLOT_COLUMN_TEMPLATE
)


def role_rank(role: str) -> int:
    """Return a seniority rank — lower is more senior. Default 999."""
    if not role:
        return 999
    lower = role.lower()
    for pattern, rank in ROLE_RANK_PATTERNS:
        if re.search(pattern, lower):
            return rank
    return 999


def collapse_roster(roster_df: pd.DataFrame) -> dict[str, list[dict]]:
    """Group team-roster rows by record_id, ordered by seniority then name."""
    grouped: dict[str, list[dict]] = {}
    for row in roster_df.to_dict(orient="records"):
        record_id = str(row.get("record_id") or "").strip()
        name = str(row.get("principal_name") or "").strip()
        if not record_id or not name:
            continue
        role = str(row.get("principal_role") or "").strip()
        source_url = str(row.get("source_url") or "").strip()
        grouped.setdefault(record_id, []).append(
            {
                "name": name,
                "role": role,
                "source_url": source_url,
                "rank": role_rank(role),
            }
        )
    for _record_id, people in grouped.items():
        people.sort(key=lambda p: (p["rank"], p["name"].lower()))
    return grouped


def build_updates(record: dict, people: list[dict]) -> dict:
    updates: dict[str, str] = {}
    if not people:
        return updates
    for slot, person in zip(PRINCIPAL_SLOTS, people[:3], strict=False):
        name_col = f"principal_{slot}_name"
        role_col = f"principal_{slot}_role"
        src_col = f"principal_{slot}_source_url"
        conf_col = f"principal_{slot}_confidence"
        existing_name = str(record.get(name_col) or "").strip()
        if existing_name:
            continue  # never overwrite an existing principal slot
        updates[name_col] = person["name"]
        if person["role"]:
            updates[role_col] = person["role"]
        if person["source_url"]:
            updates[src_col] = person["source_url"]
        updates[conf_col] = CONFIDENCE_VALUE
    return updates


@app.command("run")
def run_promotion(
    dataset: Annotated[Path, typer.Option("--dataset")] = DEFAULT_DATASET,
    roster: Annotated[Path, typer.Option("--roster")] = DEFAULT_ROSTER,
    json_output: Annotated[Path | None, typer.Option("--json-output")] = DEFAULT_JSON_OUTPUT,
) -> None:
    """Promote multi-principal columns into the validated dataset."""
    if not dataset.exists():
        raise typer.BadParameter(f"dataset not found: {dataset}")
    if not roster.exists():
        raise typer.BadParameter(f"roster file not found: {roster}")

    df = pd.read_csv(dataset).fillna("")
    roster_df = pd.read_csv(roster).fillna("")
    grouped = collapse_roster(roster_df)

    for column in ALL_SLOT_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    promoted_p1 = 0
    promoted_p2 = 0
    promoted_p3 = 0
    for index, row in df.iterrows():
        record_id = str(row.get("record_id") or "").strip()
        updates = build_updates(row.to_dict(), grouped.get(record_id, []))
        if not updates:
            continue
        for column, value in updates.items():
            df.at[index, column] = value
        if "principal_1_name" in updates:
            promoted_p1 += 1
        if "principal_2_name" in updates:
            promoted_p2 += 1
        if "principal_3_name" in updates:
            promoted_p3 += 1

    df.to_csv(dataset, index=False)
    if json_output is not None:
        json_output.write_text(
            json.dumps(df.to_dict(orient="records"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    typer.echo(
        f"Principal slots promoted: p1={promoted_p1}, p2={promoted_p2}, "
        f"p3={promoted_p3} (of {len(df)} records, "
        f"{len(grouped)} have any team roster)."
    )


if __name__ == "__main__":
    app()
