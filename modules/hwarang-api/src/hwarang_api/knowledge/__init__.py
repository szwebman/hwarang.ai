"""HLKM - Hwarang Living Knowledge Mesh

시간 인식 인과 그래프 기반 지식 시스템.

구성:
  - types: Pydantic 모델 (Fact, Edge, 관계 enum)
  - search: Temporal search (A2)
  - graph: 인과 그래프 순회 (B1)
  - contradiction: 모순 감지 3층 (B3)
  - pipeline: 수집→필터→승인→저장 파이프라인 (A4)
  - self_verify: 자가 재검증 에이전트 (A5)
  - half_life: 카테고리별 반감기 + ML 학습 (B2)
  - prediction: 예측적 사실 + 베이지안 확률 (B4)
  - entity: 엔티티 통합/정규화 (B5)
  - hrag_bridge: 기존 HRAG 통합 (A3)
  - rewards: 코인 기여 보상 (C4)
  - privacy: 개인/공용 계층 + 차등 프라이버시 (C5)
"""

from .types import (
    KnowledgeFact,
    KnowledgeEdge,
    KnowledgeStatus,
    KnowledgeVisibility,
    KnowledgeRelation,
    SearchQuery,
    SearchResult,
)
from .search import temporal_search, time_travel_search
from .graph import traverse_causal_chain, find_related
from .contradiction import detect_contradiction, explain_conflict
from .pipeline import ingest_fact, curate_batch
from .self_verify import run_daily_verification
from .half_life import current_confidence, DEFAULT_HALF_LIFE
from .prediction import predict_fact_outcome
from .entity import resolve_entity, merge_entities
from .hrag_bridge import sync_from_hrag
from .rewards import calculate_reward, pay_contribution
from .privacy import encrypt_for_user, decrypt_for_user

__all__ = [
    "KnowledgeFact",
    "KnowledgeEdge",
    "KnowledgeStatus",
    "KnowledgeVisibility",
    "KnowledgeRelation",
    "SearchQuery",
    "SearchResult",
    "temporal_search",
    "time_travel_search",
    "traverse_causal_chain",
    "find_related",
    "detect_contradiction",
    "explain_conflict",
    "ingest_fact",
    "curate_batch",
    "run_daily_verification",
    "current_confidence",
    "DEFAULT_HALF_LIFE",
    "predict_fact_outcome",
    "resolve_entity",
    "merge_entities",
    "sync_from_hrag",
    "calculate_reward",
    "pay_contribution",
    "encrypt_for_user",
    "decrypt_for_user",
]
