from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

NonEmptyStr = Annotated[str, Field(min_length=1)]
PLACEHOLDER_VALUES = {"hidden", "tbd", "todo", "dummy", "example.com"}
PLACEHOLDER_URL_DOMAINS = {"example.com", "example.org", "example.net"}


class FamilyOfficeType(StrEnum):
    single_family_office = "single_family_office"
    multi_family_office = "multi_family_office"
    family_backed_investment_firm = "family_backed_investment_firm"
    family_foundation = "family_foundation"
    unclear = "unclear"


class EvidenceQuality(StrEnum):
    primary = "primary"
    secondary = "secondary"
    tertiary = "tertiary"
    unverified = "unverified"


class RawFamilyOfficeRecord(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    record_id: NonEmptyStr
    family_office_name: NonEmptyStr
    family_office_type: FamilyOfficeType = FamilyOfficeType.unclear
    description: NonEmptyStr
    investment_thesis: str = ""
    investing_sectors: str = ""
    aum_text: str = ""
    website_url: HttpUrl
    corporate_linkedin_url: HttpUrl | None = None
    street_address: str = ""
    city: str = ""
    state_region: str = ""
    country: NonEmptyStr
    principal_name: str = ""
    principal_title: str = ""
    principal_linkedin_url: HttpUrl | None = None
    primary_email: EmailStr | None = None
    primary_phone: str = ""
    recent_activity: str = ""
    source_urls: list[HttpUrl]
    source_notes: NonEmptyStr
    extraction_method: NonEmptyStr = "manual_research"
    evidence_quality: EvidenceQuality = EvidenceQuality.unverified
    uncertainty_notes: str = ""

    @field_validator("source_urls", mode="before")
    @classmethod
    def split_source_urls(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.replace("\n", ";").split(";") if item.strip()]
        return value

    @field_validator(
        "corporate_linkedin_url",
        "principal_linkedin_url",
        "primary_email",
        mode="before",
    )
    @classmethod
    def blank_optional_fields_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("source_urls")
    @classmethod
    def require_source_urls(cls, value: list[HttpUrl]) -> list[HttpUrl]:
        if len(value) < 2:
            raise ValueError("at least two source URLs are required")
        return value

    @model_validator(mode="after")
    def reject_placeholders(self) -> RawFamilyOfficeRecord:
        for field_name, value in self.model_dump(mode="json").items():
            if value is None:
                continue
            values = value if isinstance(value, list) else [value]
            for item in values:
                if not isinstance(item, str):
                    continue
                normalized = item.strip().lower()
                if normalized in PLACEHOLDER_VALUES:
                    raise ValueError(f"{field_name} contains placeholder value: {item!r}")
                if normalized.startswith(("http://", "https://")):
                    domain = normalized.split("//", 1)[1].split("/", 1)[0].removeprefix("www.")
                    if domain in PLACEHOLDER_URL_DOMAINS:
                        raise ValueError(f"{field_name} contains placeholder URL domain: {domain}")
        return self


class UrlCheck(BaseModel):
    url: str
    status_code: int | None = None
    final_url: str | None = None
    ok: bool = False
    error: str | None = None


class ValidatedFamilyOfficeRecord(RawFamilyOfficeRecord):
    website_check: UrlCheck
    source_checks: list[UrlCheck]
    source_count: int
    validation_score: int
    confidence: str
    validation_status: str
    validation_notes: str
