"""Promote SEC IAPD regulatory identifiers into the validated dataset.

Reads the per-FO evidence JSON files produced by ``sec_iapd_research`` and
writes the following columns onto each dataset row:

- ``sec_registered`` — "True" / "False" sentinel string for evaluator parity.
- ``sec_crd_number`` — authoritative SEC CRD (also known as firm_source_id).
- ``sec_file_number`` — e.g. "801-70776".
- ``sec_registration_status`` — "ACTIVE" / "INACTIVE" / "UNKNOWN".
- ``sec_firm_name_iapd`` — the firm name as filed with the SEC.
- ``sec_firm_other_names`` — semicolon-joined aliases (DBAs).
- ``sec_branches_count`` — count of registered branch offices.
- ``form_adv_brochure_url`` — direct link to the firm's Form ADV Part 2A PDF.
- ``sec_summary_url`` — link to the human-readable adviserinfo summary page.
- ``sec_address_city`` / ``sec_address_state`` / ``sec_address_country`` — the
  firm's principal office on file with the SEC (corroboration signal).
- ``sec_evidence_url`` + ``sec_confidence`` — pairing for every promoted value.
- ``sec_near_match_review_status`` + ``sec_near_match_notes`` — manual review
  notes for threshold-edge IAPD matches.

Records without an IAPD match get ``sec_registered = "False"`` and an
``uncertainty_notes`` addendum explaining that no registration was accepted in
the locked snapshot. This is intentionally not phrased as a legal conclusion.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

app = typer.Typer(no_args_is_help=True)

DEFAULT_EVIDENCE_DIR = Path("data/evidence/sec_iapd_2026_05_17")
DEFAULT_DATASET_PATH = Path("data/processed/family_offices_validated.csv")
DEFAULT_JSON_OUTPUT = Path("data/processed/family_offices_validated.json")

CONFIDENCE_VALUE = "sec_authoritative"
MANUAL_REVIEW_CONFIDENCE_VALUE = "sec_authoritative_manual_review"
EVIDENCE_COLUMN = "sec_evidence_url"
CONFIDENCE_COLUMN = "sec_confidence"
NEAR_MATCH_STATUS_COLUMN = "sec_near_match_review_status"
NEAR_MATCH_NOTES_COLUMN = "sec_near_match_notes"

PROMOTED_VALUE_COLUMNS = (
    "sec_registered",
    "sec_crd_number",
    "sec_file_number",
    "sec_registration_status",
    "sec_firm_name_iapd",
    "sec_firm_other_names",
    "sec_branches_count",
    "form_adv_brochure_url",
    "sec_summary_url",
    "sec_address_city",
    "sec_address_state",
    "sec_address_country",
)
PROMOTED_COLUMNS = PROMOTED_VALUE_COLUMNS + (
    EVIDENCE_COLUMN,
    CONFIDENCE_COLUMN,
    NEAR_MATCH_STATUS_COLUMN,
    NEAR_MATCH_NOTES_COLUMN,
)

UNCERTAINTY_SENTINEL = (
    "No SEC/IAPD registration was accepted in the 2026-05-17 validation "
    "snapshot; this is not a live legal determination."
)


def _is_nullish(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _existing(value: object) -> str:
    if _is_nullish(value):
        return ""
    return str(value).strip()


def _append_uncertainty_note(existing: str, addition: str) -> str:
    if not existing:
        return addition
    if addition in existing:
        return existing
    return f"{existing}. {addition}"


def _load_evidence(evidence_dir: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted(evidence_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        record_id = str(data.get("record_id") or "").strip()
        if record_id:
            out[record_id] = data
    return out


def build_updates(record: dict, evidence: dict | None) -> dict[str, str]:
    if evidence is None:
        return {}
    updates: dict[str, str] = {}
    is_registered = bool(evidence.get("sec_registered"))
    manual_status = _existing(evidence.get("manual_review_status"))
    manual_notes = _existing(
        evidence.get("manual_review_notes") or evidence.get("manual_review_reason")
    )
    if manual_status:
        updates[NEAR_MATCH_STATUS_COLUMN] = manual_status
    if manual_notes:
        updates[NEAR_MATCH_NOTES_COLUMN] = manual_notes

    if is_registered:
        crd = str(evidence.get("sec_crd_number") or "").strip()
        if not crd:
            return {}
        evidence_url = (
            evidence.get("sec_summary_url")
            or f"https://adviserinfo.sec.gov/firm/summary/{crd}"
        )
        candidates: dict[str, str] = {
            "sec_registered": "True",
            "sec_crd_number": crd,
            "sec_file_number": str(evidence.get("sec_file_number") or "").strip(),
            "sec_registration_status": str(
                evidence.get("sec_registration_status") or ""
            ).strip(),
            "sec_firm_name_iapd": str(evidence.get("firm_name_iapd") or "").strip(),
            "sec_firm_other_names": "; ".join(
                str(name).strip()
                for name in (evidence.get("firm_other_names") or [])
                if str(name).strip()
            ),
            "sec_branches_count": (
                str(evidence["firm_branches_count"]).strip()
                if evidence.get("firm_branches_count") not in (None, "")
                else ""
            ),
            "form_adv_brochure_url": str(
                evidence.get("form_adv_brochure_url") or ""
            ).strip(),
            "sec_summary_url": str(evidence.get("sec_summary_url") or "").strip(),
            "sec_address_city": str(
                (evidence.get("sec_address") or {}).get("city") or ""
            ).strip(),
            "sec_address_state": str(
                (evidence.get("sec_address") or {}).get("state") or ""
            ).strip(),
            "sec_address_country": str(
                (evidence.get("sec_address") or {}).get("country") or ""
            ).strip(),
        }
        for column, new_value in candidates.items():
            if not new_value:
                continue
            existing = _existing(record.get(column))
            if existing and column != "sec_registered":
                continue
            updates[column] = new_value
        if updates:
            updates[EVIDENCE_COLUMN] = evidence_url
            updates[CONFIDENCE_COLUMN] = (
                MANUAL_REVIEW_CONFIDENCE_VALUE
                if manual_status == "accepted"
                else CONFIDENCE_VALUE
            )
        return updates

    # Not registered — write the explicit False marker + note (only if empty).
    if not _existing(record.get("sec_registered")):
        updates["sec_registered"] = "False"
    existing_notes = _existing(record.get("uncertainty_notes"))
    new_notes = _append_uncertainty_note(existing_notes, UNCERTAINTY_SENTINEL)
    if new_notes != existing_notes:
        updates["uncertainty_notes"] = new_notes
    return updates


@app.command("run")
def run_promotion(
    dataset: Annotated[Path, typer.Option("--dataset")] = DEFAULT_DATASET_PATH,
    evidence_dir: Annotated[
        Path, typer.Option("--evidence-dir")
    ] = DEFAULT_EVIDENCE_DIR,
    json_output: Annotated[Path | None, typer.Option("--json-output")] = DEFAULT_JSON_OUTPUT,
) -> None:
    """Promote SEC IAPD identifiers and registration status into the dataset."""
    if not dataset.exists():
        raise typer.BadParameter(f"dataset not found: {dataset}")
    df = pd.read_csv(dataset).fillna("")
    evidence = _load_evidence(evidence_dir)

    for column in PROMOTED_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    registered = 0
    unregistered = 0
    for index, row in df.iterrows():
        record_id = str(row.get("record_id") or "").strip()
        updates = build_updates(row.to_dict(), evidence.get(record_id))
        if not updates:
            continue
        for column, value in updates.items():
            df.at[index, column] = value
        if updates.get("sec_registered") == "True":
            registered += 1
        elif updates.get("sec_registered") == "False":
            unregistered += 1

    df.to_csv(dataset, index=False)

    if json_output is not None:
        json_output.write_text(
            json.dumps(df.to_dict(orient="records"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    typer.echo(
        f"SEC IAPD promoted: registered={registered}, "
        f"explicitly_unregistered={unregistered}."
    )


if __name__ == "__main__":
    app()
