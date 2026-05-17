from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ChunkType = Literal[
    "record_profile",
    "field_evidence",
    "regulatory",
    "recent_activity",
    "contact_policy",
]

IntentName = Literal[
    "entity_lookup",
    "regulatory",
    "contact_lookup",
    "recent_activity",
    "filtered_listing",
    "comparison",
    "unknown",
]


class ChunkMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    chunk_id: str
    record_id: str
    chunk_type: ChunkType
    family_office_name: str
    family_office_type: str = ""
    country: str = ""
    state_region: str = ""
    city: str = ""
    source_urls: list[str] = Field(default_factory=list)
    primary_source_url: str = ""
    field_name: str = ""
    field_value_text: str = ""
    evidence_quality: str = ""
    confidence_label: str = ""
    validation_status: str = ""
    validation_score: int = 0
    source_count: int = 0
    website_ok: bool = False
    sec_registered: bool = False
    sec_crd_number: str = ""
    sec_confidence: str = ""
    recent_activity_type: str = ""
    recent_activity_date: str = ""
    recent_activity_outlet: str = ""
    recent_activity_confidence: str = ""
    human_audit_status: str = ""
    auto_prescreen_flag: str = ""
    uncertainty_notes: str = ""
    data_validation_period: str = ""
    safe_answer_policy: str = "evidence_only"


class Chunk(BaseModel):
    chunk_id: str
    text: str
    metadata: ChunkMetadata


class IntentAnalysis(BaseModel):
    intent: IntentName
    requested_fields: list[str] = Field(default_factory=list)
    preferred_chunk_types: list[ChunkType] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    matched_record_ids: list[str] = Field(default_factory=list)
    matched_record_names: list[str] = Field(default_factory=list)
    needs_exact_entity: bool = False


class RetrievalHit(BaseModel):
    chunk_id: str
    record_id: str
    chunk_type: ChunkType
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float = 0.0
    dense_rank: int | None = None
    bm25_rank: int | None = None
    final_rank: int = 0
    why_retrieved: str = ""


class RetrievalResult(BaseModel):
    query: str
    intent: IntentAnalysis
    hits: list[RetrievalHit]


class AnswerCitation(BaseModel):
    record_id: str
    family_office_name: str
    chunk_id: str
    chunk_type: str
    source_url: str
    field_name: str = ""


class AnswerResult(BaseModel):
    answer: str
    confidence: Literal["high", "medium", "low"]
    abstain: bool
    caveats: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    citations: list[AnswerCitation] = Field(default_factory=list)
    unsupported_claim_count: int = 0

