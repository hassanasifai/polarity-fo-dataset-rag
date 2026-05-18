from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from src.loaders.family_offices import clean_text, to_bool
from src.schema import ChunkType, IntentAnalysis

STATE_ALIASES = {
    "alabama": "AL",
    "al": "AL",
    "alaska": "AK",
    "ak": "AK",
    "arizona": "AZ",
    "az": "AZ",
    "arkansas": "AR",
    "ar": "AR",
    "california": "CA",
    "ca": "CA",
    "new york": "NY",
    "ny": "NY",
    "ohio": "OH",
    "oh": "OH",
    "virginia": "VA",
    "va": "VA",
    "colorado": "CO",
    "co": "CO",
    "connecticut": "CT",
    "ct": "CT",
    "missouri": "MO",
    "mo": "MO",
    "texas": "TX",
    "tx": "TX",
    "florida": "FL",
    "fl": "FL",
    "massachusetts": "MA",
    "ma": "MA",
    "washington": "WA",
    "wa": "WA",
    "georgia": "GA",
    "ga": "GA",
    "illinois": "IL",
    "il": "IL",
    "pennsylvania": "PA",
    "pa": "PA",
    "south carolina": "SC",
    "sc": "SC",
    "new jersey": "NJ",
    "nj": "NJ",
    "utah": "UT",
    "ut": "UT",
    "nevada": "NV",
    "nv": "NV",
    "oregon": "OR",
    "michigan": "MI",
    "mi": "MI",
    "minnesota": "MN",
    "mn": "MN",
    "wisconsin": "WI",
    "wi": "WI",
    "indiana": "IN",
    "tennessee": "TN",
    "tn": "TN",
    "north carolina": "NC",
    "nc": "NC",
    "maryland": "MD",
    "md": "MD",
    "delaware": "DE",
    "de": "DE",
    "rhode island": "RI",
    "ri": "RI",
    "new hampshire": "NH",
    "nh": "NH",
    "vermont": "VT",
    "vt": "VT",
    "maine": "ME",
    "kentucky": "KY",
    "ky": "KY",
    "louisiana": "LA",
    "la": "LA",
    "oklahoma": "OK",
    "ok": "OK",
    "iowa": "IA",
    "ia": "IA",
    "kansas": "KS",
    "ks": "KS",
    "nebraska": "NE",
    "ne": "NE",
    "new mexico": "NM",
    "nm": "NM",
    "idaho": "ID",
    "id": "ID",
    "montana": "MT",
    "mt": "MT",
    "wyoming": "WY",
    "wy": "WY",
    "north dakota": "ND",
    "nd": "ND",
    "south dakota": "SD",
    "sd": "SD",
    "mississippi": "MS",
    "ms": "MS",
    "west virginia": "WV",
    "wv": "WV",
    "district of columbia": "DC",
    "dc": "DC",
}


def _contains_any(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def _domain(value: str) -> str:
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return parsed.netloc.removeprefix("www.")


def _identifier_variants(value: Any) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    variants = [text]
    if re.fullmatch(r"\d+\.0", text):
        variants.append(text[:-2])
    return list(dict.fromkeys(variants))


def _preferred_chunk_types(intent: str, requested_fields: list[str]) -> list[ChunkType]:
    if intent == "regulatory":
        return ["regulatory", "field_evidence", "record_profile"]
    if intent == "contact_lookup":
        if "corporate_linkedin_url" in requested_fields:
            return ["field_evidence", "record_profile", "contact_policy"]
        return ["contact_policy", "field_evidence", "record_profile"]
    if intent == "recent_activity":
        return ["recent_activity", "record_profile"]
    if intent == "filtered_listing":
        return ["record_profile", "regulatory", "recent_activity", "contact_policy"]
    if intent == "comparison":
        return ["record_profile", "regulatory", "contact_policy", "recent_activity"]
    if "corporate_linkedin_url" in requested_fields:
        return ["field_evidence", "record_profile", "contact_policy"]
    if any(field in requested_fields for field in ["aum_text", "principal_linkedin_url"]):
        return ["contact_policy", "field_evidence", "record_profile"]
    return ["record_profile", "field_evidence", "regulatory", "recent_activity", "contact_policy"]


def _linkedin_requested_field(text: str) -> str:
    principal_terms = ["principal", "personal", "private", "individual", "founder", "owner"]
    corporate_terms = ["corporate", "company", "company page", "public", "firm", "business"]
    if _contains_any(text, principal_terms) and not _contains_any(text, corporate_terms):
        return "principal_linkedin_url"
    return "corporate_linkedin_url"


def _requested_fields(text: str) -> list[str]:
    fields: list[str] = []
    if _contains_any(text, ["email", "e-mail", "contact"]) or re.search(
        r"[\w.+-]+@[\w.-]+\.[a-z]{2,}",
        text,
    ):
        fields.append("primary_email")
    if _contains_any(text, ["phone", "telephone", "number", "contact"]):
        fields.append("primary_phone")
    if "linkedin" in text:
        fields.append(_linkedin_requested_field(text))
    if _contains_any(text, ["aum", "assets under management"]):
        fields.append("aum_text")
    if _contains_any(text, ["sec", "crd", "iad", "registered", "registration"]):
        fields.extend(["sec_registered", "sec_crd_number"])
    if _contains_any(text, ["recent", "activity", "news", "latest", "current"]):
        fields.append("recent_activity")
    return list(dict.fromkeys(fields))


def _match_records(text: str, records: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    matched: list[tuple[int, str, str]] = []
    for record in records:
        name = clean_text(record.get("family_office_name"))
        if not name:
            continue
        lowered_name = name.lower()
        if lowered_name in text:
            matched.append((len(lowered_name), clean_text(record.get("record_id")), name))
            continue
        exact_fields = [
            clean_text(record.get("primary_email")),
            clean_text(record.get("primary_phone")),
            clean_text(record.get("google_places_phone")),
            clean_text(record.get("website_url")),
            clean_text(record.get("corporate_linkedin_url")),
        ]
        exact_fields.extend(_identifier_variants(record.get("sec_crd_number")))
        exact_fields.extend(_domain(value) for value in list(exact_fields) if value and "." in value)
        if any(value and value.lower() in text for value in exact_fields):
            matched.append((80, clean_text(record.get("record_id")), name))
            continue
        name_tokens = [token for token in re.findall(r"[a-z0-9]+", lowered_name) if len(token) > 2]
        if len(name_tokens) >= 2 and all(token in text for token in name_tokens[: min(3, len(name_tokens))]):
            matched.append((sum(len(token) for token in name_tokens), clean_text(record.get("record_id")), name))
            continue
        crd_variants = _identifier_variants(record.get("sec_crd_number"))
        if any(crd and crd in text for crd in crd_variants):
            matched.append((max(len(crd) for crd in crd_variants) + 50, clean_text(record.get("record_id")), name))
    matched.sort(reverse=True)
    ids = [record_id for _, record_id, _ in matched]
    names = [name for _, _, name in matched]
    return list(dict.fromkeys(ids)), list(dict.fromkeys(names))


def parse_filters(text: str) -> dict[str, Any]:
    text = text.lower()
    filters: dict[str, Any] = {}
    if _contains_any(text, ["sec-registered", "sec registered", "registered investment adviser"]):
        filters["sec_registered"] = True
    if _contains_any(text, ["not sec registered", "not sec-registered", "non-sec", "no sec"]):
        filters["sec_registered"] = False
    if "single family" in text or "single-family" in text:
        filters["family_office_type"] = "single_family_office"
    if "multi family" in text or "multi-family" in text:
        filters["family_office_type"] = "multi_family_office"
    if "linkedin" in text and _contains_any(text, ["public", "company page", "presence", "with"]):
        filters["has_corporate_linkedin"] = True
    for alias, state_code in STATE_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", text):
            filters["state_region"] = state_code
            if alias == "california":
                filters["state_or_city"] = "California"
            break
    for country in [
        "united states",
        "usa",
        "us",
        "uk",
        "united kingdom",
        "switzerland",
        "india",
        "belgium",
        "germany",
        "japan",
        "australia",
        "singapore",
        "hong kong",
        "isle of man",
    ]:
        if re.search(rf"\b{re.escape(country)}\b", text):
            filters["country"] = {
                "usa": "United States",
                "us": "United States",
                "united states": "United States",
                "uk": "United Kingdom",
                "united kingdom": "United Kingdom",
                "switzerland": "Switzerland",
                "india": "India",
                "belgium": "Belgium",
                "germany": "Germany",
                "japan": "Japan",
                "australia": "Australia",
                "singapore": "Singapore",
                "hong kong": "Hong Kong",
                "isle of man": "Isle of Man",
            }[country]
            break
    return filters


def record_matches_filters(record: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        if key == "state_or_city":
            state = clean_text(record.get("state_region")).lower()
            city = clean_text(record.get("city")).lower()
            expected_text = clean_text(expected).lower()
            state_filter = clean_text(filters.get("state_region")).lower()
            if state != state_filter.lower() and city != expected_text:
                return False
            continue
        if key == "state_region" and "state_or_city" in filters:
            continue
        if key == "has_corporate_linkedin":
            if bool(clean_text(record.get("corporate_linkedin_url"))) is not bool(expected):
                return False
            continue
        if key == "sec_registered":
            if to_bool(record.get(key)) is not bool(expected):
                return False
            continue
        if clean_text(record.get(key)).lower() != clean_text(expected).lower():
            return False
    return True


def metadata_matches_filters(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        if key == "state_or_city":
            state = clean_text(metadata.get("state_region")).lower()
            city = clean_text(metadata.get("city")).lower()
            expected_text = clean_text(expected).lower()
            state_filter = clean_text(filters.get("state_region")).lower()
            if state != state_filter and city != expected_text:
                return False
            continue
        if key == "state_region" and "state_or_city" in filters:
            continue
        if key == "has_corporate_linkedin":
            has_linkedin = clean_text(metadata.get("field_name")) == "corporate_linkedin_url" and bool(
                clean_text(metadata.get("field_value_text"))
            )
            if has_linkedin is not bool(expected):
                return False
            continue
        if key == "sec_registered":
            if to_bool(metadata.get(key)) is not bool(expected):
                return False
            continue
        if clean_text(metadata.get(key)).lower() != clean_text(expected).lower():
            return False
    return True


def classify_intent(query: str, records: list[dict[str, Any]] | None = None) -> IntentAnalysis:
    text = query.lower()
    requested_fields = _requested_fields(text)
    filters = parse_filters(text)
    asks_record_resolution = _contains_any(
        text,
        ["which record", "which firm", "which family office", "which office"],
    )
    asks_corporate_linkedin_value = "corporate_linkedin_url" in requested_fields and not asks_record_resolution
    is_listing_question = _contains_any(text, ["which", "list", "show me all", "find all"]) and (
        "family offices" in text or bool(filters)
    )

    if _contains_any(text, ["compare", "versus", " vs "]):
        intent = "comparison"
    elif is_listing_question:
        intent = "filtered_listing"
    elif asks_corporate_linkedin_value or any(
        field in requested_fields for field in ["primary_email", "primary_phone", "principal_linkedin_url", "aum_text"]
    ):
        intent = "contact_lookup"
    elif any(field in requested_fields for field in ["sec_registered", "sec_crd_number"]):
        intent = "regulatory"
    elif "recent_activity" in requested_fields:
        intent = "recent_activity"
    else:
        intent = "entity_lookup"

    matched_ids: list[str] = []
    matched_names: list[str] = []
    if records:
        matched_ids, matched_names = _match_records(text, records)
    if matched_ids and intent in {"entity_lookup", "contact_lookup", "regulatory", "recent_activity"}:
        filters.pop("sec_registered", None)
    needs_exact_entity = intent in {"entity_lookup", "contact_lookup", "regulatory", "recent_activity"} and bool(
        matched_ids
    )
    return IntentAnalysis(
        intent=intent,  # type: ignore[arg-type]
        requested_fields=requested_fields,
        preferred_chunk_types=_preferred_chunk_types(intent, requested_fields),
        filters=filters,
        matched_record_ids=matched_ids,
        matched_record_names=matched_names,
        needs_exact_entity=needs_exact_entity,
    )
