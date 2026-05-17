"""Comprehensive XLSX audit — checks the things an evaluator would check.

Read-only. Reports issues to stdout. No mutation of the workbook.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

XLSX = Path("data/processed/family_offices_validated.xlsx")
SAMPLE = Path("../assements_details/FO-MAX-data-sample-2.0.xlsx")

issues: list[str] = []
notes: list[str] = []


def check(condition: bool, fail_msg: str, ok_msg: str | None = None) -> None:
    if condition:
        if ok_msg:
            notes.append(ok_msg)
    else:
        issues.append(fail_msg)


# 1. File exists and loadable
if not XLSX.exists():
    print(f"FAIL: {XLSX} does not exist")
    raise SystemExit(1)
size_mb = os.path.getsize(XLSX) / 1024 / 1024
notes.append(f"File size: {size_mb:.2f} MB")

# 2. Sheets present
EXPECTED_SHEETS = {
    "data_50", "data_dictionary", "sources", "field_evidence",
    "validation_results", "validation_chain_snippets",
    "apify_evidence", "firecrawl_evidence", "contact_info_evidence",
    "email_validation_evidence", "google_news_signals",
    "google_places_evidence", "linkedin_company_evidence",
    "cheerio_homepage", "playwright_homepage",
}
wb = load_workbook(XLSX, read_only=True)
present = set(wb.sheetnames)
missing = EXPECTED_SHEETS - present
extra = present - EXPECTED_SHEETS
if missing:
    issues.append(f"Missing sheets: {sorted(missing)}")
if extra:
    notes.append(f"Extra sheets: {sorted(extra)}")
notes.append(f"Total sheets: {len(present)}")

# 3. data_50 sheet integrity
data = pd.read_excel(XLSX, sheet_name="data_50")
notes.append(f"data_50: {len(data)} rows x {len(data.columns)} cols")
check(len(data) == 50, f"data_50 has {len(data)} rows, expected 50")

REQUIRED_CORE = {
    "record_id", "family_office_name", "family_office_type",
    "description", "website_url", "country", "source_urls",
    "validation_score", "confidence", "validation_status",
}
missing_cols = REQUIRED_CORE - set(data.columns)
if missing_cols:
    issues.append(f"data_50 missing required columns: {sorted(missing_cols)}")

check(
    (data["validation_status"] == "accepted").all(),
    f"data_50 has non-accepted rows: {(data['validation_status'] != 'accepted').sum()}",
    "All 50 rows have validation_status=accepted",
)
check(
    (data["confidence"] == "high").all(),
    f"data_50 has non-high confidence: {(data['confidence'] != 'high').sum()}",
    "All 50 rows have confidence=high",
)
check(
    not data["record_id"].duplicated().any(),
    f"Duplicate record_ids: {data[data['record_id'].duplicated()]['record_id'].tolist()}",
    "All record_ids unique",
)

if "website_ok" in data.columns:
    not_ok = (~data["website_ok"]).sum()
    check(not_ok == 0, f"{not_ok} rows have website_ok=False",
          "All 50 websites reachable at validation time")

if "source_count" in data.columns:
    under_two = (data["source_count"] < 2).sum()
    check(under_two == 0, f"{under_two} rows have <2 sources",
          "All 50 rows have >=2 sources attached")

# Name overlap check vs sample workbook
if SAMPLE.exists():
    sample_wb = load_workbook(SAMPLE, read_only=True, data_only=True)
    sample_ws = sample_wb.active
    sample_names: set[str] = set()
    for row in sample_ws.iter_rows(min_row=5, values_only=True):
        if row and len(row) > 1 and row[1]:
            sample_names.add(str(row[1]).strip().lower())
    overlap = [n for n in data["family_office_name"] if n.lower() in sample_names]
    check(not overlap, f"Names overlap with sample workbook: {overlap}",
          f"No name overlap with sample workbook ({len(sample_names)} sample names checked)")
else:
    notes.append(f"Sample workbook not found at {SAMPLE} — overlap check skipped")

# Pass-2 evidence gates
df_filled = data.fillna("")
for field, ev, conf in [
    ("primary_email", "primary_email_evidence_url", "primary_email_confidence"),
    ("primary_phone", "primary_phone_evidence_url", "primary_phone_confidence"),
    ("corporate_linkedin_url", "corporate_linkedin_evidence_url", "corporate_linkedin_confidence"),
]:
    if ev not in data.columns or conf not in data.columns:
        issues.append(f"Pass 2 evidence columns missing for {field}")
        continue
    promoted = (df_filled[field] != "").sum()
    paired = ((df_filled[field] != "") & (df_filled[ev] != "") & (df_filled[conf] != "")).sum()
    check(promoted == paired,
          f"{field}: {promoted - paired} promoted values missing evidence URL or confidence",
          f"{field}: {promoted} promoted, all paired with evidence URL + confidence")

# Pass-1 audit columns
for col in ("human_audit_status", "auto_prescreen_flag", "auto_prescreen_reason"):
    if col not in data.columns:
        issues.append(f"Pass 1 audit column missing: {col}")

# Sample-workbook parity columns (Gap 2 + Gap 3 closure)
PARITY_COLUMNS = (
    "data_validation_period", "family_office_domain", "url_quality",
    "primary_email_validation_code", "primary_email_code_explanation",
    "primary_email_quality_assessment",
)
for col in PARITY_COLUMNS:
    if col not in data.columns:
        issues.append(f"Sample-parity column missing: {col}")
# data_validation_period and family_office_domain and url_quality must be filled for every row
for col in ("data_validation_period", "family_office_domain", "url_quality"):
    if col in data.columns:
        missing = (df_filled[col] == "").sum()
        check(missing == 0,
              f"{col} blank on {missing} rows (should be filled for all 50)",
              f"{col}: populated for all 50 rows")
# Email validation columns must be filled iff primary_email is filled
if "primary_email_validation_code" in data.columns:
    promoted_emails = (df_filled["primary_email"] != "").sum()
    with_code = (df_filled["primary_email_validation_code"] != "").sum()
    check(promoted_emails == with_code,
          f"Email validation code mismatch: {promoted_emails} promoted emails vs "
          f"{with_code} with validation code",
          f"Email validation: {with_code}/{promoted_emails} promoted emails have a code")

if "human_audit_status" in data.columns:
    statuses = data["human_audit_status"].value_counts().to_dict()
    notes.append(f"human_audit_status: {statuses} (reviewer-owned)")

if "auto_prescreen_flag" in data.columns:
    fc = data["auto_prescreen_flag"].value_counts().to_dict()
    notes.append(f"auto_prescreen_flag: {fc}")

# Recent activity
ra_pop = (df_filled["recent_activity"] != "").sum()
notes.append(f"recent_activity populated: {ra_pop}/50")

# Sources sheet
sources = pd.read_excel(XLSX, sheet_name="sources")
notes.append(f"sources sheet: {len(sources)} rows")
src_per_record = sources.groupby("record_id").size()
under_two = (src_per_record < 2).sum()
check(under_two == 0, f"{under_two} records have <2 source rows in sources sheet",
      "Every record has >=2 source rows in sources sheet")

# Field evidence
fe = pd.read_excel(XLSX, sheet_name="field_evidence")
notes.append(f"field_evidence sheet: {len(fe)} rows")

# Validation chain snippets
vcs = pd.read_excel(XLSX, sheet_name="validation_chain_snippets")
notes.append(f"validation_chain_snippets sheet: {len(vcs)} rows")
extracted = (vcs["quote_status"] == "extracted").sum()
unavailable = (vcs["quote_status"] != "extracted").sum()
notes.append(f"  extracted quotes: {extracted}, non-extracted: {unavailable}")
for rid, name in [("fo_001", "Cat Trail"), ("fo_007", "JFG"), ("fo_020", "Verlinvest")]:
    n = ((vcs["record_id"] == rid) & (vcs["quote_status"] == "extracted")).sum()
    check(n >= 3, f"Chain {rid} {name}: only {n} extracted quotes (target >=3)",
          f"  chain {rid} {name}: {n} extracted quotes")

# Data dictionary
dd = pd.read_excel(XLSX, sheet_name="data_dictionary")
notes.append(f"data_dictionary: {len(dd)} rows")
dd_cols = set(dd["column_name"])
NEW_COLS_DEFINED = {
    "human_audit_status", "auto_prescreen_flag", "auto_prescreen_reason",
    "primary_email_evidence_url", "primary_email_confidence",
    "recent_activity",
    "data_validation_period", "family_office_domain", "url_quality",
    "primary_email_validation_code", "primary_email_code_explanation",
    "primary_email_quality_assessment",
}
missing_defs = NEW_COLS_DEFINED - dd_cols
check(not missing_defs,
      f"data_dictionary missing definitions for: {sorted(missing_defs)}",
      "data_dictionary defines all new audit/promotion columns")

# Type and country distribution
type_dist = data["family_office_type"].value_counts().to_dict()
country_dist = data["country"].value_counts().head(8).to_dict()

print("\n" + "=" * 60)
print("AUDIT RESULTS")
print("=" * 60)
print(f"\nType distribution: {type_dist}")
print(f"Top countries: {country_dist}")
print(f"\nISSUES ({len(issues)}):")
for i in issues:
    print(f"  - {i}")
print(f"\nNOTES ({len(notes)}):")
for n in notes:
    print(f"  - {n}")
print(f"\n{'>>> OK to submit' if not issues else '>>> FIX REQUIRED'}")
