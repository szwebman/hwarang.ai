"""HLKM 공통 타입 정의.

Pydantic 모델 + enum. 다른 모듈들이 공유.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class KnowledgeStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    PENDING = "PENDING"
    PREDICTED = "PREDICTED"
    EXPIRED = "EXPIRED"
    RETRACTED = "RETRACTED"
    DISPUTED = "DISPUTED"


class KnowledgeVisibility(str, Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    TEAM = "TEAM"
    RESTRICTED = "RESTRICTED"


class KnowledgeRelation(str, Enum):
    CAUSES = "CAUSES"
    ENABLES = "ENABLES"
    CONTRADICTS = "CONTRADICTS"
    SUPPORTS = "SUPPORTS"
    DERIVED_FROM = "DERIVED_FROM"
    RELATED_TO = "RELATED_TO"
    SPECIALIZES = "SPECIALIZES"
    GENERALIZES = "GENERALIZES"
    TEMPORAL_AFTER = "TEMPORAL_AFTER"
    ALTERNATIVE_TO = "ALTERNATIVE_TO"


class KnowledgeFact(BaseModel):
    id: str | None = None
    content: str
    content_hash: str | None = None
    embedding: list[float] | None = None

    domain: str = "general"
    entity: str | None = None
    tags: list[str] = []
    language: str = "ko"

    valid_from: datetime
    valid_to: datetime | None = None
    created_at: datetime | None = None
    last_verified_at: datetime | None = None
    next_check_at: datetime | None = None

    confidence_t0: float = 1.0
    half_life_days: int | None = None

    status: KnowledgeStatus = KnowledgeStatus.CONFIRMED
    predicted_valid_from: datetime | None = None
    prediction_confidence: float | None = None
    expired_reason: str | None = None

    source: str
    source_url: str | None = None
    source_type: Literal["user", "crawl", "official", "agent", "community"] = "user"

    visibility: KnowledgeVisibility = KnowledgeVisibility.PUBLIC
    owner_user_id: str | None = None

    supersedes_id: str | None = None
    contributed_by: str | None = None
    reward_paid: int = 0


class KnowledgeEdge(BaseModel):
    id: str | None = None
    from_fact_id: str
    to_fact_id: str
    relation_type: KnowledgeRelation
    strength: float = 1.0
    evidence: str | None = None
    verified_by: Literal["ai", "human", "consensus"] = "ai"
    created_at: datetime | None = None


class SearchQuery(BaseModel):
    query: str
    as_of_date: datetime | None = None  # None = 현재
    domain: str | None = None
    user_id: str | None = None          # 개인 지식 검색 시
    include_private: bool = False
    include_predicted: bool = False
    min_confidence: float = 0.0
    limit: int = 10


class SearchResult(BaseModel):
    facts: list[KnowledgeFact]
    current_confidences: list[float]   # facts와 동일 길이. 시간 감쇠 적용된 현재 신뢰도
    contradictions: list[tuple[str, str]] = []  # (fact_a_id, fact_b_id)
    as_of_date: datetime
    query_time_ms: float


class ContradictionReport(BaseModel):
    is_contradiction: bool
    confidence: float
    reasoning: str
    resolution_hint: str | None = None


class PredictionOutcome(BaseModel):
    predicted_valid_from: datetime
    confidence: float
    rationale: str
    contributing_signals: list[str] = []


class VerificationResult(BaseModel):
    fact_id: str
    method: Literal["source_refetch", "llm_check", "cross_source", "community"]
    result: Literal["unchanged", "updated", "invalidated", "source_gone"]
    confidence_delta: float
    notes: str | None = None
    new_content: str | None = None  # 'updated'일 때 새 내용
