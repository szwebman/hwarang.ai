"""사고 사이클의 누적 메모리 (Phase 6 — Master Cognitive Loop).

매 사이클의 (관찰, 추론, 결정, 결과) 를 ``CognitiveMemory`` 에 저장.
다음 사이클이 비슷한 상황에서 과거 결정/결과 (lesson) 를 참조해
LLM 추론의 컨텍스트로 사용한다.

스토어
------
``prisma.cognitivememory`` (스키마 정의는 ``hwarang-web/prisma/schema.prisma``).
``observedEmbedding`` / ``reasoningEmbedding`` 은 pgvector ``vector(384)`` 컬럼 —
Prisma 가 ``Unsupported`` 로 모델링하므로 raw SQL 로만 읽고 쓴다.

주요 함수
---------
* ``record_decision()`` — 새 결정 기록 + 자동 임베딩, ID 반환
* ``update_outcome()`` — 결과 기록 (다음 사이클이 lesson 참조)
* ``find_similar_past_decisions()`` — pgvector 코사인 유사도 검색
* ``get_recent_lessons()`` — 최근 lesson 만 추출 (추론 프롬프트용)

폴백
----
pgvector 미설치 / 임베딩 실패 시 자동으로 ``actor + outcome`` 휴리스틱 폴백.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from hwarang_api.cognitive.embeddings import (
    embed_observation,
    embed_reasoning,
    to_pgvector_literal,
)
from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    id: str
    actor: str
    timestamp: datetime
    observed: dict
    reasoning: str
    decision: str
    action_taken: str | None
    outcome: str | None
    outcome_score: float | None
    lesson: str | None
    similarity: float | None = None  # pgvector 검색일 때만 채워짐 (1.0 = 동일)


async def record_decision(
    actor: str,
    observed: dict,
    reasoning: str,
    decision: str,
    action_taken: str | None = None,
) -> str:
    """새 결정 기록. 생성된 CognitiveMemory id 반환.

    Args:
        actor: "master" 또는 "agent_<id>"
        observed: 관찰한 상태 (json-serializable dict)
        reasoning: LLM chain-of-thought (5000자 잘림)
        decision: 결정 내용 (3000자 잘림)
        action_taken: 즉시 알 수 있으면 함께 기록 (아니면 나중에 update)

    Returns:
        새로 생성된 CognitiveMemory.id

    구현 노트
    --------
    1) prisma.cognitivememory.create 로 일반 컬럼 저장
    2) raw SQL UPDATE 로 vector 컬럼 채움 — Prisma 가 vector 타입 미지원
       임베딩 실패 시 임베딩만 NULL 로 남고, 나머지 데이터는 정상.
    """
    try:
        record = await prisma.cognitivememory.create(
            data={
                "actor": actor,
                "timestamp": datetime.now(timezone.utc),
                "observed": observed,
                "reasoning": (reasoning or "")[:5000],
                "decision": (decision or "")[:3000],
                "actionTaken": action_taken,
            }
        )
        memory_id = record.id
    except Exception as exc:  # noqa: BLE001
        logger.warning("record_decision 실패: %s", exc)
        return ""

    # 임베딩 생성 + 저장 (실패해도 본 레코드는 살아있음)
    try:
        obs_emb = await embed_observation(observed) if observed else None
        reason_emb = await embed_reasoning(reasoning) if reasoning else None

        if obs_emb is not None:
            await _set_embedding(memory_id, "observedEmbedding", obs_emb)
        if reason_emb is not None:
            await _set_embedding(memory_id, "reasoningEmbedding", reason_emb)
    except Exception as exc:  # noqa: BLE001
        logger.debug("임베딩 저장 실패 (%s): %s", memory_id, exc)

    return memory_id


async def _set_embedding(memory_id: str, column: str, emb: list[float]) -> None:
    """pgvector 컬럼에 raw SQL 로 임베딩 저장.

    column 은 "observedEmbedding" | "reasoningEmbedding" — 화이트리스트.
    pgvector 확장이 없으면 조용히 실패.
    """
    if column not in ("observedEmbedding", "reasoningEmbedding"):
        raise ValueError(f"unknown vector column: {column}")
    literal = to_pgvector_literal(emb)
    try:
        await prisma.execute_raw(
            f'UPDATE "CognitiveMemory" SET "{column}" = $1::vector WHERE id = $2',
            literal,
            memory_id,
        )
    except Exception as exc:  # noqa: BLE001
        # pgvector 확장 / 컬럼 없을 때 — 운영 모드에서는 setup_pgvector.sh 로 해결.
        logger.debug("vector 컬럼 (%s) 업데이트 실패: %s", column, exc)


async def update_outcome(
    memory_id: str,
    outcome: str,
    score: float,
    lesson: str | None = None,
) -> None:
    """결과 기록 — 다음 사이클이 이 lesson 을 참조한다.

    Args:
        memory_id: ``record_decision`` 이 반환한 id
        outcome: 결과 요약 (2000자 잘림)
        score: -1.0 ~ +1.0 범위 (음수=후회, 양수=좋은 결정)
        lesson: 한 줄 교훈 (1000자 잘림). None 이면 lesson 미기록.
    """
    if not memory_id:
        return
    try:
        await prisma.cognitivememory.update(
            where={"id": memory_id},
            data={
                "outcome": (outcome or "")[:2000],
                "outcomeScore": score,
                "lesson": (lesson[:1000] if lesson else None),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("update_outcome 실패 (%s): %s", memory_id, exc)


async def find_similar_past_decisions(
    current_observation: dict,
    actor: str,
    top_k: int = 5,
) -> list[MemoryEntry]:
    """현재 상황과 비슷한 과거 결정 검색 — pgvector 코사인 유사도.

    1) current_observation → 384-dim 벡터
    2) ``CognitiveMemory.observedEmbedding`` 과 코사인 거리 (``<=>``) 정렬
    3) outcomeScore 가 채워진 (= 결과까지 알려진) 항목만
    4) 임베딩/확장 실패 시 ``_fallback_recent`` (시간 기반)

    Returns:
        유사도 내림차순으로 정렬된 ``MemoryEntry`` 리스트.
        ``MemoryEntry.similarity`` 에 0~1 점수 (1=동일).
    """
    obs_emb = None
    try:
        obs_emb = await embed_observation(current_observation)
    except Exception as exc:  # noqa: BLE001
        logger.debug("쿼리 임베딩 실패: %s", exc)

    if obs_emb is None:
        return await _fallback_recent(actor, top_k)

    literal = to_pgvector_literal(obs_emb)
    try:
        rows = await prisma.query_raw(
            '''
            SELECT id, actor, timestamp, observed, reasoning, decision,
                   "actionTaken" AS action_taken,
                   outcome, "outcomeScore" AS outcome_score, lesson,
                   1 - ("observedEmbedding" <=> $1::vector) AS similarity
            FROM "CognitiveMemory"
            WHERE actor = $2
              AND "observedEmbedding" IS NOT NULL
              AND "outcomeScore" IS NOT NULL
            ORDER BY "observedEmbedding" <=> $1::vector
            LIMIT $3
            ''',
            literal, actor, top_k,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("pgvector 검색 실패, 폴백 사용: %s", exc)
        return await _fallback_recent(actor, top_k)

    entries: list[MemoryEntry] = []
    for r in rows or []:
        entries.append(
            MemoryEntry(
                id=_get(r, "id"),
                actor=_get(r, "actor"),
                timestamp=_get(r, "timestamp"),
                observed=_get(r, "observed") or {},
                reasoning=_get(r, "reasoning") or "",
                decision=_get(r, "decision") or "",
                action_taken=_get(r, "action_taken"),
                outcome=_get(r, "outcome"),
                outcome_score=_get(r, "outcome_score"),
                lesson=_get(r, "lesson"),
                similarity=float(_get(r, "similarity") or 0.0),
            )
        )
    return entries


def _get(row, key: str):
    """dict / namedtuple-like row 양쪽 호환."""
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


async def _fallback_recent(actor: str, top_k: int) -> list[MemoryEntry]:
    """pgvector 미사용 환경 — actor + outcomeScore 존재 + 최신순."""
    try:
        records = await prisma.cognitivememory.find_many(
            where={"actor": actor, "outcomeScore": {"not": None}},
            order={"timestamp": "desc"},
            take=top_k,
        )
        return [_to_dataclass(r) for r in records]
    except Exception as exc:  # noqa: BLE001
        logger.warning("_fallback_recent 실패: %s", exc)
        return []


async def get_recent_lessons(actor: str, limit: int = 10) -> list[str]:
    """최근 배운 교훈만 추출 — 추론 시 컨텍스트로."""
    try:
        records = await prisma.cognitivememory.find_many(
            where={"actor": actor, "lesson": {"not": None}},
            order={"timestamp": "desc"},
            take=limit,
        )
        return [r.lesson for r in records if getattr(r, "lesson", None)]
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_recent_lessons 실패: %s", exc)
        return []


def _to_dataclass(r) -> MemoryEntry:
    return MemoryEntry(
        id=r.id,
        actor=r.actor,
        timestamp=r.timestamp,
        observed=r.observed,
        reasoning=r.reasoning,
        decision=r.decision,
        action_taken=getattr(r, "actionTaken", None),
        outcome=getattr(r, "outcome", None),
        outcome_score=getattr(r, "outcomeScore", None),
        lesson=getattr(r, "lesson", None),
        similarity=None,
    )


__all__ = [
    "MemoryEntry",
    "record_decision",
    "update_outcome",
    "find_similar_past_decisions",
    "get_recent_lessons",
]
