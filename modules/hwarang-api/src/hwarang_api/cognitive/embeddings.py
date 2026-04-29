"""Cognitive Memory 임베딩 유틸 — observation / reasoning 을 384-dim 벡터로.

`hwarang_api.knowledge.embeddings` 의 ``embed_text`` 를 재사용하지만,
pgvector 의 ``vector(384)`` 컬럼에 맞춰 차원을 강제 보정한다.

핵심 함수
---------
* ``embed_observation(dict)`` — observation dict 의 의미있는 키만 골라 텍스트화 → 벡터
* ``embed_reasoning(str)``    — chain-of-thought 의 앞 2000자 → 벡터
* ``cosine_similarity(a, b)`` — 폴백용 순수 Python 코사인 (pgvector 미사용 시)

NOTE: ``embed_text`` 가 기본 1024 차원 (bge-m3) 을 돌려주므로, 384 차원으로
잘라/패딩한다. 의미 손실은 있지만 pgvector 의 HNSW 인덱스 효율과 트레이드.
"""

from __future__ import annotations

import logging
from typing import Optional

from hwarang_api.knowledge.embeddings import embed_text

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384

# observation 에서 의미있는 키만 추출하기 위한 화이트리스트 — master_loop 가
# 채우는 표준 키 + 도메인별 동적 키 (facts_*, rlhf_*) 는 prefix 매칭.
_IMPORTANT_KEYS: tuple[str, ...] = (
    "rlhf_satisfaction_7d",
    "rlhf_count_7d",
    "rounds_7d",
    "open_gaps",
    "pending_decisions",
    "active_agents",
    "new_facts_24h",
    "crawl_queue_pending",
    "domain",
    "candidates",
    "consulted",
    "willing",
    "declining",
    "min_willing",
)
_IMPORTANT_PREFIXES: tuple[str, ...] = (
    "facts_",
    "rlhf_",
    "round_",
    "agent_",
    "model_",
)


def _fit_dim(vec: list[float], dim: int = EMBEDDING_DIM) -> list[float]:
    """차원 보정 — 길면 자르고, 짧으면 0-패딩."""
    if not vec:
        return [0.0] * dim
    if len(vec) >= dim:
        return [float(x) for x in vec[:dim]]
    return [float(x) for x in vec] + [0.0] * (dim - len(vec))


def _observation_to_text(observation: dict) -> str:
    """observation dict → 임베딩용 텍스트.

    중요 키 우선, 그 외 prefix 매칭 키도 포함. 알수없는 dict/list 값은
    str() 로 잘라 1000자로 제한 (긴 metadata 가 임베딩 노이즈가 되지 않게).
    """
    if not isinstance(observation, dict):
        return str(observation)[:2000]

    parts: list[str] = []
    seen: set[str] = set()

    for k in _IMPORTANT_KEYS:
        if k in observation:
            v = observation[k]
            parts.append(f"{k}={_short_repr(v)}")
            seen.add(k)

    for k, v in observation.items():
        if k in seen:
            continue
        if any(k.startswith(p) for p in _IMPORTANT_PREFIXES):
            parts.append(f"{k}={_short_repr(v)}")

    return " | ".join(parts)


def _short_repr(v) -> str:
    """긴 nested 값은 100자로 자름."""
    s = str(v)
    if len(s) > 100:
        return s[:100] + "…"
    return s


async def embed_observation(observation: dict) -> Optional[list[float]]:
    """observation dict → 384-dim 벡터. 빈 텍스트면 None."""
    text = _observation_to_text(observation)
    if not text:
        return None
    try:
        emb = await embed_text(text)
        if emb:
            return _fit_dim(emb)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("observation 임베딩 실패: %s", exc)
        return None


async def embed_reasoning(reasoning: str) -> Optional[list[float]]:
    """reasoning 텍스트 임베딩. 너무 짧으면 (10자 미만) None."""
    if not reasoning or len(reasoning) < 10:
        return None
    try:
        emb = await embed_text(reasoning[:2000])
        if emb:
            return _fit_dim(emb)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("reasoning 임베딩 실패: %s", exc)
        return None


def to_pgvector_literal(emb: list[float]) -> str:
    """[0.1, 0.2, ...] → pgvector 리터럴 문자열 ``[0.1,0.2,...]``."""
    return "[" + ",".join(f"{float(x):.6f}" for x in emb) + "]"


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """순수 Python 코사인 (pgvector 미사용 폴백)."""
    if not a or not b:
        return 0.0
    import math

    n = min(len(a), len(b))
    dot = sum(float(a[i]) * float(b[i]) for i in range(n))
    na = math.sqrt(sum(float(x) * float(x) for x in a[:n]))
    nb = math.sqrt(sum(float(x) * float(x) for x in b[:n]))
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (na * nb)


__all__ = [
    "EMBEDDING_DIM",
    "embed_observation",
    "embed_reasoning",
    "to_pgvector_literal",
    "cosine_similarity",
]
