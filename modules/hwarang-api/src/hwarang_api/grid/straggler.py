"""StragglerHandler — 느린 에이전트 탐지 / 재할당.

기존 ``grid.py`` 는 timeout 처리가 없어서 한 명의 느린 에이전트가
라운드 전체를 정체시켰다. 이 모듈은 주기적으로 호출되어:

* ACCEPTED 상태로 ``timeout_seconds`` 가 지난 에이전트 → ``TIMEOUT`` 처리
* 평판 감점 (-0.05)
* 라운드 최소 참여자 수 미달 시 :class:`AgentMatcher` 로 추가 모집
* 결과를 dict 로 반환 (orchestrator 가 이를 받아 broadcast)

cron / background task 또는 RoundOrchestrator 에서 직접 호출 가능.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


REPUTATION_PENALTY_TIMEOUT = 0.05
DEFAULT_MIN_PARTICIPANTS = 3


class StragglerHandler:
    """느린 에이전트 탐지 / 대응."""

    def __init__(
        self,
        matcher: Any | None = None,
        min_participants: int = DEFAULT_MIN_PARTICIPANTS,
        active_agents_provider: Callable[[], list[dict[str, Any]]] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        matcher
            :class:`AgentMatcher` 인스턴스. ``reassign`` 에서 사용. 순환 참조 방지를
            위해 lazy import.
        min_participants
            라운드의 최소 활성 참여자 수.
        active_agents_provider
            현재 활성 에이전트 dict 리스트를 반환하는 callable.
            grid.py 에서 ``_agents`` 를 넘겨주는 식. None 이면 폴백.
        """
        self._matcher = matcher
        self.min_participants = min_participants
        self._active_agents_provider = active_agents_provider

    # ──────────────────────────────────────────────────────
    # 라운드 점검
    # ──────────────────────────────────────────────────────
    async def check_round(
        self,
        round_id: str,
        timeout_seconds: int = 600,
    ) -> dict[str, Any]:
        """라운드의 느린 에이전트 탐지 + 후속 조치.

        Returns
        -------
        dict
            ``{"timed_out": [...], "promoted": [...], "round_status": "RUNNING"|"FAILED"}``
        """
        try:
            from hwarang_api.db import prisma  # type: ignore
        except Exception:
            prisma = None  # type: ignore[assignment]

        timed_out: list[str] = []
        promoted: list[str] = []
        round_status = "RUNNING"

        connected = prisma is not None and getattr(prisma, "is_connected", lambda: False)()

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)

        if connected:
            try:
                participants = await prisma.roundparticipant.find_many(  # type: ignore[attr-defined]
                    where={
                        "roundId": round_id,
                        "status": {"in": ["ACCEPTED", "INVITED"]},
                    },
                )
            except Exception as e:
                logger.warning("RoundParticipant 조회 실패: %s", e)
                participants = []

            for p in participants:
                joined_at = getattr(p, "joinedAt", None)
                # joinedAt 이 cutoff 보다 오래되었고 아직 SUBMITTED 가 아니면 timeout
                if joined_at is None or joined_at >= cutoff:
                    continue

                agent_id = getattr(p, "agentId", None)
                if not agent_id:
                    continue

                try:
                    await prisma.roundparticipant.update(  # type: ignore[attr-defined]
                        where={"id": p.id},
                        data={"status": "TIMEOUT"},
                    )
                    timed_out.append(agent_id)
                    await self._penalize_reputation(agent_id, REPUTATION_PENALTY_TIMEOUT)
                except Exception as e:
                    logger.warning("TIMEOUT 처리 실패 (%s): %s", agent_id, e)

            # 남은 active 참가자 수 확인
            try:
                remaining = await prisma.roundparticipant.count(  # type: ignore[attr-defined]
                    where={
                        "roundId": round_id,
                        "status": {"in": ["ACCEPTED", "SUBMITTED"]},
                    },
                )
            except Exception as e:
                logger.warning("remaining count 실패: %s", e)
                remaining = 0

            if remaining < self.min_participants:
                needed = self.min_participants - remaining
                logger.info(
                    "round %s 미달 (%d/%d) → 추가 모집 시도 (%d명)",
                    round_id, remaining, self.min_participants, needed,
                )
                promoted = await self.reassign(round_id, additional_count=needed)
                if remaining + len(promoted) < self.min_participants:
                    round_status = "FAILED"
                    try:
                        await prisma.round.update(  # type: ignore[attr-defined]
                            where={"id": round_id},
                            data={"status": "FAILED"},
                        )
                    except Exception as e:
                        logger.warning("Round.status=FAILED 갱신 실패: %s", e)
        else:
            logger.debug("Prisma 미연결 — straggler check skip")

        return {
            "round_id": round_id,
            "timed_out": timed_out,
            "promoted": promoted,
            "round_status": round_status,
        }

    # ──────────────────────────────────────────────────────
    # 추가 모집
    # ──────────────────────────────────────────────────────
    async def reassign(
        self,
        round_id: str,
        additional_count: int,
    ) -> list[str]:
        """추가 에이전트 모집.

        AgentMatcher 가 주입돼 있고 active_agents_provider 가 있으면 그것을
        통해 신규 후보를 점수화. 부족하면 빈 리스트.
        """
        if additional_count <= 0:
            return []
        if self._matcher is None or self._active_agents_provider is None:
            logger.warning("matcher 또는 active_agents_provider 미설정 — reassign 불가")
            return []

        # 라운드 도메인 조회
        round_domain = "general"
        try:
            from hwarang_api.db import prisma  # type: ignore

            if getattr(prisma, "is_connected", lambda: False)():
                row = await prisma.round.find_unique(where={"id": round_id})  # type: ignore[attr-defined]
                if row is not None and getattr(row, "domain", None):
                    round_domain = row.domain  # type: ignore[assignment]
        except Exception:
            pass

        # 이미 라운드에 들어간 에이전트는 제외
        existing: set[str] = set()
        try:
            from hwarang_api.db import prisma  # type: ignore

            if getattr(prisma, "is_connected", lambda: False)():
                rows = await prisma.roundparticipant.find_many(  # type: ignore[attr-defined]
                    where={"roundId": round_id},
                )
                existing = {getattr(r, "agentId", None) for r in rows if getattr(r, "agentId", None)}
        except Exception:
            existing = set()

        try:
            agents = self._active_agents_provider() or []
        except Exception as e:
            logger.warning("active_agents_provider 호출 실패: %s", e)
            return []

        candidates_pool = [a for a in agents if a.get("agent_id") not in existing]
        if not candidates_pool:
            return []

        try:
            ranked = await self._matcher.rank_candidates(
                round_domain=round_domain,
                active_agents=candidates_pool,
                target_count=additional_count,
            )
        except Exception as e:
            logger.warning("rank_candidates 실패: %s", e)
            return []

        promoted_ids: list[str] = []
        try:
            from hwarang_api.db import prisma  # type: ignore

            connected = getattr(prisma, "is_connected", lambda: False)()
        except Exception:
            connected = False

        for cand in ranked:
            agent_id = cand.agent_id
            if connected:
                try:
                    await prisma.roundparticipant.upsert(  # type: ignore[attr-defined]
                        where={
                            "roundId_agentId": {
                                "roundId": round_id,
                                "agentId": agent_id,
                            }
                        },
                        data={
                            "create": {
                                "roundId": round_id,
                                "agentId": agent_id,
                                "status": "ACCEPTED",
                            },
                            "update": {"status": "ACCEPTED"},
                        },
                    )
                except Exception as e:
                    logger.warning("RoundParticipant upsert 실패 (%s): %s", agent_id, e)
                    continue
            promoted_ids.append(agent_id)

        return promoted_ids

    # ──────────────────────────────────────────────────────
    # 평판 감점
    # ──────────────────────────────────────────────────────
    @staticmethod
    async def _penalize_reputation(agent_id: str, penalty: float) -> None:
        """ContributorProfile.reputation 감점 (있을 때만)."""
        try:
            from hwarang_api.db import prisma  # type: ignore
        except Exception:
            return
        if not getattr(prisma, "is_connected", lambda: False)():
            return

        try:
            profile = await prisma.contributorprofile.find_unique(  # type: ignore[attr-defined]
                where={"userId": agent_id},
            )
            if profile is None:
                return
            new_rep = max(0.0, float(getattr(profile, "reputation", 0.5)) - penalty)
            await prisma.contributorprofile.update(  # type: ignore[attr-defined]
                where={"userId": agent_id},
                data={"reputation": new_rep},
            )
            logger.info("reputation -%.2f → %.2f for %s", penalty, new_rep, agent_id)
        except Exception as e:
            logger.debug("reputation penalty 실패(무시) (%s): %s", agent_id, e)


__all__ = ["StragglerHandler"]
