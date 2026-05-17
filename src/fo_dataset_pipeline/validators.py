from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse

import dns.exception
import dns.resolver
import httpx

from fo_dataset_pipeline.models import RawFamilyOfficeRecord, UrlCheck, ValidatedFamilyOfficeRecord

DISCOVERY_ONLY_DOMAINS = {
    "dev.swfinstitute.org",
    "swfinstitute.org",
}


def normalize_entity_name(name: str) -> str:
    normalized = name.casefold()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    suffixes = {
        "ag",
        "co",
        "company",
        "corp",
        "corporation",
        "inc",
        "limited",
        "llc",
        "lp",
        "ltd",
        "plc",
        "pte",
    }
    parts = [part for part in normalized.split() if part not in suffixes]
    return " ".join(parts)


def find_name_overlaps(candidate_names: list[str], blocked_names: set[str]) -> list[str]:
    blocked_normalized = {normalize_entity_name(name) for name in blocked_names}
    return [
        name
        for name in candidate_names
        if normalize_entity_name(name) in blocked_normalized
    ]


async def check_url(client: httpx.AsyncClient, url: str) -> UrlCheck:
    try:
        response = await client.get(url, follow_redirects=True)
        return UrlCheck(
            url=url,
            status_code=response.status_code,
            final_url=str(response.url),
            ok=response.status_code < 400,
        )
    except httpx.HTTPError as exc:
        return UrlCheck(url=url, ok=False, error=str(exc))


def has_dns(domain: str) -> bool:
    try:
        dns.resolver.resolve(domain, "A")
        return True
    except (dns.exception.DNSException, ValueError):
        return False


def domain_from_url(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def has_discovery_only_sources(record: RawFamilyOfficeRecord) -> bool:
    return any(domain_from_url(str(url)) in DISCOVERY_ONLY_DOMAINS for url in record.source_urls)


def score_record(
    record: RawFamilyOfficeRecord,
    website_check: UrlCheck,
    source_checks: list[UrlCheck],
) -> tuple[int, str, str, str]:
    score = 0
    notes: list[str] = []

    if record.family_office_name:
        score += 8
    if record.family_office_type.value != "unclear":
        score += 8
    else:
        notes.append("family office type is unclear")
    if record.description:
        score += 8
    if record.investment_thesis:
        score += 6
    if record.investing_sectors:
        score += 6
    if website_check.ok:
        score += 12
    else:
        domain = domain_from_url(str(record.website_url))
        if has_dns(domain):
            score += 4
            notes.append("website request failed but DNS resolves")
        else:
            notes.append("website request failed and DNS did not resolve")
    ok_sources = sum(1 for check in source_checks if check.ok)
    if len(record.source_urls) >= 2:
        score += 12
    else:
        notes.append("fewer than two source URLs")
    score += min(ok_sources * 6, 18)
    if record.evidence_quality.value == "primary":
        score += 10
    elif record.evidence_quality.value == "secondary":
        score += 6
    elif record.evidence_quality.value == "tertiary":
        score += 3
    else:
        notes.append("evidence quality is unverified")
    if record.principal_name and record.principal_title:
        score += 6
    if record.recent_activity:
        score += 6

    if ok_sources < 2:
        notes.append("fewer than two source URLs were reachable")
    if has_discovery_only_sources(record):
        notes.append("source URLs include discovery-only directory sources")

    confidence = "high" if score >= 80 else "medium" if score >= 60 else "low"
    status = (
        "accepted"
        if (
            score >= 80
            and website_check.ok
            and len(record.source_urls) >= 2
            and ok_sources >= 2
            and not has_discovery_only_sources(record)
        )
        else "needs_review"
    )
    return (
        min(score, 100),
        confidence,
        "; ".join(notes) or "passed configured validation checks",
        status,
    )


async def validate_records(
    records: list[RawFamilyOfficeRecord],
) -> list[ValidatedFamilyOfficeRecord]:
    headers = {"User-Agent": "PolarityIQ-assessment-validation/0.1"}
    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        validated: list[ValidatedFamilyOfficeRecord] = []
        for record in records:
            website_check = await check_url(client, str(record.website_url))
            source_checks = await asyncio.gather(
                *(check_url(client, str(url)) for url in record.source_urls)
            )
            score, confidence, notes, status = score_record(
                record,
                website_check,
                list(source_checks),
            )
            validated.append(
                ValidatedFamilyOfficeRecord(
                    **record.model_dump(),
                    website_check=website_check,
                    source_checks=list(source_checks),
                    source_count=len(record.source_urls),
                    validation_score=score,
                    confidence=confidence,
                    validation_status=status,
                    validation_notes=notes,
                )
            )
        return validated
