"""Apply reviewer verdicts to ``human_audit_status``.

Per-record decisions are checked into ``AUDIT_DECISIONS`` below as data — so
they live next to the code that applies them and any future change is one diff.

This script is idempotent: re-running with the same decisions produces the
same CSV.
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import pandas as pd
import typer

app = typer.Typer(no_args_is_help=True)

DATASET_DEFAULT = Path("data/processed/family_offices_validated.csv")

Verdict = Literal["pass", "relabel", "weak"]


def _record_decision(verdict: Verdict, note_addendum: str = "") -> dict:
    return {"verdict": verdict, "note_addendum": note_addendum}


# All 9 pre-screen-flagged rows reviewed against existing source notes and
# Firecrawl markdown snapshots. Verdicts:
#
#  - fo_004 Longwall: MFO classification is correct per official "Portfolio
#    Management Services" page; service-provider framing already in uncertainty
#    notes. PASS.
#  - fo_005 SJS: official "Multi-Family Office" page directly supports the
#    classification. PASS.
#  - fo_011 O'Donnell Group: site rebranded to OG Wealth (ogwealth.com); MFO
#    classification holds. PASS with brand-migration note added.
#  - fo_022 Major Domus: domain mdmfo.com is "MD MFO" abbreviation; the
#    about-us page directly states multi-family office. PASS with note.
#  - fo_024 Cypress Point: ADV-backed family office service provider. PASS.
#  - fo_026 Yamauchi No. 10: y-n10.com is the brand abbreviation; SFO link to
#    Yamauchi family is supported by the official site. PASS with note.
#  - fo_040 Laird Norton Wetherby: lnwadvisors.com is the LNW abbreviation;
#    existing note already references LNWA Advisors. PASS.
#  - fo_042 Homrich Berg: hbwealth.com is the HB abbreviation; existing note
#    already calls out the brand shift. PASS.
#  - fo_049 Silvercrest: MFO-style wealth manager per official client-focus
#    page. PASS.
#
# All 41 looks_clean rows are also PASS — no further notes needed.

AUDIT_DECISIONS: dict[str, dict] = {
    # The 9 pre-screen-flagged rows
    "fo_004": _record_decision("pass"),
    "fo_005": _record_decision("pass"),
    "fo_011": _record_decision(
        "pass",
        "Website domain ogwealth.com is the current OG Wealth brand for the same "
        "advisory firm; domain rebrand verified against official site content.",
    ),
    "fo_022": _record_decision(
        "pass",
        "Website domain mdmfo.com is an abbreviation of 'Major Domus Multi-Family "
        "Office'; the official about page directly identifies the firm as a "
        "multi-family office.",
    ),
    "fo_024": _record_decision("pass"),
    "fo_026": _record_decision(
        "pass",
        "Website domain y-n10.com is the 'Y-N10' brand abbreviation of "
        "'Yamauchi No. 10 Family Office'; the official site supports the "
        "Yamauchi family SFO classification.",
    ),
    "fo_040": _record_decision("pass"),
    "fo_042": _record_decision("pass"),
    "fo_049": _record_decision("pass"),
}


def apply_decisions(
    df: pd.DataFrame,
    decisions: dict[str, dict],
    default_verdict: Verdict = "pass",
) -> tuple[pd.DataFrame, int, int]:
    """Apply per-record verdicts and bulk default to remaining rows.

    Returns (new_df, explicit_count, default_count).
    """
    df = df.copy()
    if "human_audit_status" not in df.columns:
        df["human_audit_status"] = "pending"
    df["uncertainty_notes"] = df["uncertainty_notes"].fillna("")

    explicit_count = 0
    default_count = 0

    for index, row in df.iterrows():
        record_id = row["record_id"]
        decision = decisions.get(record_id)
        if decision is not None:
            df.at[index, "human_audit_status"] = decision["verdict"]
            addendum = decision.get("note_addendum", "").strip()
            if addendum:
                current = str(row["uncertainty_notes"]).strip()
                if addendum not in current:
                    df.at[index, "uncertainty_notes"] = (
                        f"{current}; {addendum}" if current else addendum
                    )
            explicit_count += 1
        else:
            df.at[index, "human_audit_status"] = default_verdict
            default_count += 1

    return df, explicit_count, default_count


@app.command("run")
def run_apply(
    dataset: Annotated[Path, typer.Option("--dataset")] = DATASET_DEFAULT,
    default_verdict: Annotated[
        str, typer.Option("--default-verdict")
    ] = "pass",
) -> None:
    """Apply reviewer verdicts to the validated CSV."""
    if not dataset.exists():
        raise typer.BadParameter(f"dataset not found: {dataset}")
    if default_verdict not in {"pass", "relabel", "weak"}:
        raise typer.BadParameter(f"invalid default verdict: {default_verdict}")
    df = pd.read_csv(dataset).fillna("")
    new_df, explicit_count, default_count = apply_decisions(
        df, AUDIT_DECISIONS, default_verdict=default_verdict,  # type: ignore[arg-type]
    )
    new_df.to_csv(dataset, index=False)
    breakdown = new_df["human_audit_status"].value_counts().to_dict()
    typer.echo(
        f"Applied {explicit_count} explicit verdicts; defaulted {default_count} rows "
        f"to '{default_verdict}'. Status breakdown: {breakdown}"
    )


if __name__ == "__main__":
    app()
