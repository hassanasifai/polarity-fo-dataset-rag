"""Pass 2 — Promote corporate-level contact intelligence with evidence flags.

Promotion rules (deliberately conservative, HVL-aligned):

- Only **corporate** contact fields are promoted (``primary_email``,
  ``primary_phone``, ``corporate_linkedin_url``).
- ``principal_*`` fields are NOT promoted — we have no public-source evidence
  that ties a specific person's email/phone/LinkedIn to a principal role.
- Every promoted value gets a sibling ``*_evidence_url`` (where it was found)
  and ``*_confidence`` label. A value is promoted only when BOTH the value and
  the evidence URL exist; otherwise the cell stays blank.

The module rewrites the validated CSV in place and regenerates the JSON copy.
The XLSX is left for the Pass-4 final regeneration pass.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import pandas as pd
import typer

app = typer.Typer(no_args_is_help=True)

CORPORATE_EMAIL_LOCALS = {
    "info", "contact", "hello", "admin", "office", "enquiries", "inquiries",
    "reception", "team", "investments", "investor", "investorrelations",
    "ir", "general", "mail",
}
EMAIL_RE = re.compile(r"^[\w.+\-]+@[\w\-]+(\.[\w\-]+)+$")
PHONE_NORMALIZE_RE = re.compile(r"[^\d+]")
COMPANY_LINKEDIN_RE = re.compile(r"linkedin\.com/(company|school)/", re.IGNORECASE)

CONTACT_EVIDENCE_PATH = Path("data/processed/contact_info_evidence.csv")
LINKEDIN_EVIDENCE_PATH = Path("data/processed/linkedin_company_evidence.csv")

PROMOTED_COLUMNS = (
    "primary_email_evidence_url",
    "primary_email_confidence",
    "primary_phone_evidence_url",
    "primary_phone_confidence",
    "corporate_linkedin_evidence_url",
    "corporate_linkedin_confidence",
)


def _domain(url: str) -> str:
    if not url or pd.isna(url):
        return ""
    netloc = urlparse(str(url)).netloc.lower().removeprefix("www.")
    return netloc


def _split_semicolon(value: object) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [item.strip() for item in str(value).split(";") if item.strip()]


def pick_corporate_email(emails_field: object, fo_domain: str) -> str | None:
    """Return the strongest corporate email match, or None."""
    candidates = [e.lower() for e in _split_semicolon(emails_field) if EMAIL_RE.match(e.strip())]
    if not candidates:
        return None

    same_domain = [e for e in candidates if e.split("@", 1)[1] == fo_domain]
    pool = same_domain or candidates

    for email in pool:
        local = email.split("@", 1)[0]
        if local in CORPORATE_EMAIL_LOCALS:
            return email
    for email in pool:
        local = email.split("@", 1)[0]
        if any(local.startswith(prefix) for prefix in CORPORATE_EMAIL_LOCALS):
            return email
    return None


def pick_phone(phones_field: object) -> str | None:
    raw_candidates = _split_semicolon(phones_field)
    for raw in raw_candidates:
        normalized = PHONE_NORMALIZE_RE.sub("", raw)
        digits = re.sub(r"\D", "", normalized)
        if len(digits) >= 7:
            return raw
    return None


def pick_company_linkedin(linkedins_field: object) -> str | None:
    for url in _split_semicolon(linkedins_field):
        if COMPANY_LINKEDIN_RE.search(url):
            return url
    return None


def load_contact_lookup(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    lookup: dict[str, dict] = {}
    for row in df.to_dict(orient="records"):
        domain = _domain(row.get("original_start_url", ""))
        if domain:
            lookup[domain] = row
    return lookup


def load_linkedin_lookup(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    lookup: dict[str, dict] = {}
    for row in df.to_dict(orient="records"):
        website_domain = _domain(row.get("website", ""))
        linkedin_url = str(row.get("linkedinUrl") or "").strip()
        if website_domain and linkedin_url and COMPANY_LINKEDIN_RE.search(linkedin_url):
            lookup[website_domain] = row
    return lookup


def promote_row(
    record: dict,
    contact_evidence: dict | None,
    linkedin_evidence: dict | None,
) -> dict:
    """Return updated cells for the record. Empty values are skipped."""
    updates: dict[str, str] = {}
    website_url = str(record.get("website_url") or "")
    fo_domain = _domain(website_url)
    contact_url = (
        contact_evidence.get("original_start_url", website_url) if contact_evidence else ""
    )

    if contact_evidence and not record.get("primary_email"):
        email = pick_corporate_email(contact_evidence.get("emails"), fo_domain)
        if email:
            updates["primary_email"] = email
            updates["primary_email_evidence_url"] = contact_url
            updates["primary_email_confidence"] = "corporate_public_listed"

    if contact_evidence and not record.get("primary_phone"):
        phone = pick_phone(contact_evidence.get("phones"))
        if phone:
            updates["primary_phone"] = phone
            updates["primary_phone_evidence_url"] = contact_url
            updates["primary_phone_confidence"] = "corporate_public_listed"

    if not record.get("corporate_linkedin_url"):
        linkedin_url: str | None = None
        confidence: str | None = None
        evidence_url: str | None = None
        if linkedin_evidence:
            linkedin_url = str(linkedin_evidence.get("linkedinUrl") or "").strip() or None
            if linkedin_url:
                confidence = "linkedin_scraped_match"
                evidence_url = linkedin_url
        if not linkedin_url and contact_evidence:
            candidate = pick_company_linkedin(contact_evidence.get("linkedins"))
            if candidate:
                linkedin_url = candidate
                confidence = "linked_from_official_site"
                evidence_url = contact_url or candidate
        if linkedin_url and evidence_url and confidence:
            updates["corporate_linkedin_url"] = linkedin_url
            updates["corporate_linkedin_evidence_url"] = evidence_url
            updates["corporate_linkedin_confidence"] = confidence

    return updates


@app.command("run")
def run_promotion(
    dataset: Annotated[Path, typer.Option("--dataset")] = Path(
        "data/processed/family_offices_validated.csv"
    ),
    contact_evidence: Annotated[
        Path, typer.Option("--contact-evidence")
    ] = CONTACT_EVIDENCE_PATH,
    linkedin_evidence: Annotated[
        Path, typer.Option("--linkedin-evidence")
    ] = LINKEDIN_EVIDENCE_PATH,
    json_output: Annotated[Path | None, typer.Option("--json-output")] = Path(
        "data/processed/family_offices_validated.json"
    ),
) -> None:
    """Promote corporate-level contact info into the validated dataset."""
    if not dataset.exists():
        raise typer.BadParameter(f"dataset not found: {dataset}")
    df = pd.read_csv(dataset).fillna("")
    contact_lookup = load_contact_lookup(contact_evidence)
    linkedin_lookup = load_linkedin_lookup(linkedin_evidence)

    for column in PROMOTED_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    promoted_email = 0
    promoted_phone = 0
    promoted_linkedin = 0
    for index, row in df.iterrows():
        fo_domain = _domain(row.get("website_url", ""))
        updates = promote_row(
            row.to_dict(),
            contact_lookup.get(fo_domain),
            linkedin_lookup.get(fo_domain),
        )
        for column, value in updates.items():
            df.at[index, column] = value
        if "primary_email" in updates:
            promoted_email += 1
        if "primary_phone" in updates:
            promoted_phone += 1
        if "corporate_linkedin_url" in updates:
            promoted_linkedin += 1

    df.to_csv(dataset, index=False)

    if json_output is not None:
        json_output.write_text(
            json.dumps(df.to_dict(orient="records"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    typer.echo(
        f"Promoted: email={promoted_email}, phone={promoted_phone}, "
        f"corporate_linkedin={promoted_linkedin} (of {len(df)} records)"
    )


if __name__ == "__main__":
    app()
