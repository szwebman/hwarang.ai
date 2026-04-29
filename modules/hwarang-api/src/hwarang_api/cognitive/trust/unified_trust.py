"""화랑 통합 신뢰 시스템 — Agent vs Source 평판 분리 유지하되 단일 인터페이스 제공.

화랑은 두 종류의 신뢰를 추적한다:

- **Agent Trust**: 분산 에이전트의 작업 수행 신뢰도 (성공률, 분쟁 승률).
  ``hwarang_api.grid.social.reputation`` (Prisma ``AgentReputation``).
- **Source Trust**: 지식 출처(URL/도메인/소스명)의 사실 정확도.
  ``hwarang_api.knowledge.reputation`` (Prisma ``SourceReputation``).

이 모듈은 두 시스템을 통합 조회할 수 있는 facade 만 제공한다.
실제 저장은 각 도메인 모듈이 그대로 담당한다 (단일 책임 유지). 저장 스키마는
현재 의도적으로 분리되어 있고, 합칠 계획은 없다 — 도메인이 다르고 업데이트
트리거가 다르고 시간 감쇠 정책이 다르기 때문이다.

공식 / 트리거 / 사용처 비교는 ``docs/TRUST_SYSTEM.md`` 참조.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 모듈 import — 한 쪽이 누락되어도 facade 는 동작해야 한다.
# ─────────────────────────────────────────────
try:  # noqa: SIM105
    from hwarang_api.grid.social import reputation as _agent_rep  # type: ignore
except Exception as exc:  # noqa: BLE001
    logger.warning("unified_trust: agent reputation 모듈 import 실패: %s", exc)
    _agent_rep = None  # type: ignore[assignment]

try:  # noqa: SIM105
    from hwarang_api.knowledge import reputation as _source_rep  # type: ignore
except Exception as exc:  # noqa: BLE001
    logger.warning("unified_trust: source reputation 모듈 import 실패: %s", exc)
    _source_rep = None  # type: ignore[assignment]


class TrustKind(str, Enum):
    """신뢰 도메인 식별자."""

    AGENT = "agent"      # 작업 수행 능력 (성공/실패/분쟁/품질)
    SOURCE = "source"    # 사실 정확도 (재검증 결과 누적)


class TrustNotAvailable(RuntimeError):
    """요청한 도메인의 평판 모듈이 import 되지 않은 환경."""


def _require(kind: TrustKind) -> Any:
    """해당 도메인 모듈을 반환하거나 예외."""
    if kind is TrustKind.AGENT:
        if _agent_rep is None:
            raise TrustNotAvailable("agent reputation module unavailable")
        return _agent_rep
    if kind is TrustKind.SOURCE:
        if _source_rep is None:
            raise TrustNotAvailable("source reputation module unavailable")
        return _source_rep
    raise ValueError(f"unknown TrustKind: {kind}")


class UnifiedTrust:
    """Agent / Source 평판을 같은 모양의 API 로 조회한다.

    각 메서드는 도메인 모듈의 함수에 단순 위임한다. 결과 dict 의 키는
    도메인별로 다르므로(예: agent 는 ``trustScore``, source 는 ``reputation``)
    원본 키와 함께 정규화된 ``score`` 키를 같이 채워 반환한다.
    """

    @staticmethod
    async def get_trust(kind: TrustKind, entity_id: str) -> float:
        """대표 신뢰 점수 (0~1).

        - AGENT: ``get_trust_score(agent_id)``
        - SOURCE: ``get_reputation(source)``
        """
        mod = _require(kind)
        if kind is TrustKind.AGENT:
            return float(await mod.get_trust_score(entity_id))
        return float(await mod.get_reputation(entity_id))

    @staticmethod
    async def get_breakdown(kind: TrustKind, entity_id: str) -> dict:
        """세부 카운터/메타까지 포함한 상세 dict.

        반환에는 ``kind``, ``entity_id``, ``score`` (정규화) 가 항상 들어간다.
        AGENT 의 경우 ``get_reputation`` 의 dict 를 그대로 합치고,
        SOURCE 는 카운터를 별도 조회할 함수가 없어 점수만 + ``list_reputations``
        에서 일치 항목을 찾아 보강한다.
        """
        mod = _require(kind)
        if kind is TrustKind.AGENT:
            full = await mod.get_reputation(entity_id)
            score = float(full.get("trustScore", 0.5))
            return {
                "kind": kind.value,
                "entity_id": entity_id,
                "score": score,
                **full,
            }

        # SOURCE: 점수 + 가능한 경우 메타까지
        score = float(await mod.get_reputation(entity_id))
        meta: Optional[dict] = None
        try:
            rows = await mod.list_reputations(min_facts=0, order_by="reputation")
            for row in rows:
                if row.get("source") == entity_id:
                    meta = row
                    break
        except Exception as exc:  # noqa: BLE001
            logger.debug("unified_trust: source meta 조회 실패: %s", exc)
        out: dict = {
            "kind": kind.value,
            "entity_id": entity_id,
            "score": score,
        }
        if meta is not None:
            out.update(meta)
        return out

    @staticmethod
    async def top_n(kind: TrustKind, n: int = 10) -> list[dict]:
        """상위 N 명/N 출처 리더보드."""
        mod = _require(kind)
        n = max(1, min(int(n), 100))
        if kind is TrustKind.AGENT:
            rows = await mod.top_agents(n=n)
            return [
                {
                    "kind": kind.value,
                    "entity_id": r.get("agentId"),
                    "score": float(r.get("trustScore", 0.0)),
                    **r,
                }
                for r in rows
            ]
        rows = await mod.list_reputations(min_facts=0, order_by="reputation")
        rows = rows[:n]
        return [
            {
                "kind": kind.value,
                "entity_id": r.get("source"),
                "score": float(r.get("reputation", 0.0)),
                **r,
            }
            for r in rows
        ]

    @staticmethod
    async def compare(kind: TrustKind, ids: list[str]) -> list[dict]:
        """여러 entity 의 점수를 한 번에 조회 (정렬 없이 입력 순서 유지)."""
        out: list[dict] = []
        for eid in ids:
            try:
                score = await UnifiedTrust.get_trust(kind, eid)
            except TrustNotAvailable:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "unified_trust.compare: %s/%s 조회 실패: %s", kind.value, eid, exc
                )
                score = 0.0
            out.append(
                {"kind": kind.value, "entity_id": eid, "score": float(score)}
            )
        return out


__all__ = ["TrustKind", "TrustNotAvailable", "UnifiedTrust"]
