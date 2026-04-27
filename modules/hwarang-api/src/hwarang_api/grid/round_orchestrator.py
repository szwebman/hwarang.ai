"""RoundOrchestrator — 라운드 라이프사이클 통합.

:class:`AgentMatcher` + :class:`DataShardingService` + :class:`StragglerHandler`
를 묶어, ``grid.py`` 의 라우터가 짧은 함수 한두 개만 호출하면 라운드를
열고 닫을 수 있도록 한다.

순환 참조 회피:
    ``broadcast_round_event`` 는 ``hwarang_api.routers.grid`` 에 정의되어
    있어 직접 import 하면 ``grid.py`` ↔ ``grid/`` 사이 순환이 생긴다.
    그래서 ``open_round`` / ``complete_round`` 는 callback 인자로 받는다.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from .matcher import AgentMatcher
from .sharder import DataShardingService
from .straggler import StragglerHandler

logger = logging.getLogger(__name__)


BroadcastFn = Callable[..., Awaitable[None]]


class RoundOrchestrator:
    """라운드 라이프사이클 통합 관리."""

    def __init__(
        self,
        matcher: AgentMatcher,
        sharder: DataShardingService,
        straggler: StragglerHandler,
    ) -> None:
        self.matcher = matcher
        self.sharder = sharder
        self.straggler = straggler

    # ──────────────────────────────────────────────────────
    # OPEN
    # ──────────────────────────────────────────────────────
    async def open_round(
        self,
        domain: str,
        data_source_url: str,
        sample_count: int,
        target_participants: int = 10,
        strategy: str = "iid",
        active_agents: list[dict[str, Any]] | None = None,
        config: dict[str, Any] | None = None,
        region: str | None = None,
        validation_fraction: float = 0.15,
        broadcast: BroadcastFn | None = None,
    ) -> dict[str, Any]:
        """라운드 생성 + 후보 선정 + 샤드 계획 + DB 레코드 + 웹소켓 fanout.

        Parameters
        ----------
        domain
            라운드 도메인 (예: ``"law"`` / ``"medical"`` / ``"code"`` / ``"general"``).
        data_source_url
            샘플 원본 URL.
        sample_count
            샘플 총 개수.
        target_participants
            매칭할 목표 참가자 수.
        strategy
            샤딩 전략 (``iid`` / ``non_iid`` / ``domain_partition``).
        active_agents
            heartbeat 결과. 없으면 빈 리스트.
        config
            HFL 학습 config (lora_r, lr 등). 그대로 ``Round.config`` 에 저장.
        region
            라운드 region.
        validation_fraction
            peer 평가용 데이터 비율.
        broadcast
            ``broadcast_round_event(event_type, round_id, domain, metadata, target_agents)``
            형태의 async callable. ``None`` 이면 fanout skip.
        """
        active_agents = list(active_agents or [])
        cfg = dict(config or {})

        # 1) 후보 선정
        candidates = await self.matcher.rank_candidates(
            round_domain=domain,
            active_agents=active_agents,
            target_count=target_participants,
            round_region=region,
        )
        chosen_ids = [c.agent_id for c in candidates]

        if not chosen_ids:
            return {
                "status": "no_candidates",
                "round_id": None,
                "selected": [],
                "shards": [],
            }

        # 2) Round 생성 (Prisma 또는 in-memory)
        round_id = await self._create_round(
            domain=domain,
            config=cfg,
            validation_fraction=validation_fraction,
        )

        # 3) RoundParticipant 작성
        await self._invite_participants(round_id, chosen_ids)

        # 4) 샤드 계획 (검증 분리 + 전략 적용)
        agent_meta_for_shard: list[dict[str, Any]] = []
        for cand in candidates:
            meta = next((a for a in active_agents if a.get("agent_id") == cand.agent_id), {})
            agent_meta_for_shard.append({
                "agent_id": cand.agent_id,
                "domains": meta.get("domains") or meta.get("expert_tags") or [],
            })

        plan = await self.sharder.plan(
            round_id=round_id,
            agents=agent_meta_for_shard,
            data_source_url=data_source_url,
            sample_count=sample_count,
            strategy=strategy,  # type: ignore[arg-type]
            validation_fraction=validation_fraction,
        )

        # 5) RoundParticipant 의 shardId 매핑 (있을 때만)
        await self._attach_shards(round_id, plan)

        # 6) Round.status = RUNNING + startedAt
        await self._mark_round_running(round_id)

        # 7) websocket fanout
        if broadcast is not None:
            try:
                await broadcast(
                    "round_open",
                    round_id,
                    domain,
                    {
                        "config": cfg,
                        "participants": chosen_ids,
                        "shards": [
                            {
                                "agent_id": s["agent_id"],
                                "shard_idx": s["shard_idx"],
                                "data_url": s["data_url"],
                                "sample_count": s["sample_count"],
                            }
                            for s in plan.shards
                        ],
                    },
                    chosen_ids,
                )
            except Exception as e:
                logger.warning("broadcast_round_event 실패 (무시): %s", e)

        return {
            "status": "opened",
            "round_id": round_id,
            "domain": domain,
            "selected": [
                {
                    "agent_id": c.agent_id,
                    "score": c.score,
                    "reasons": c.reasons,
                }
                for c in candidates
            ],
            "shards": plan.shards,
            "validation_shard": plan.validation_shard,
        }

    # ──────────────────────────────────────────────────────
    # COMPLETE
    # ──────────────────────────────────────────────────────
    async def complete_round(
        self,
        round_id: str,
        merged_lora_path: str | None = None,
        new_lora_version: int | None = None,
        broadcast: BroadcastFn | None = None,
        reward_calculator: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        """라운드 종료 처리 — 평균 quality + reward 기록 + fanout.

        실제 LoRA FedAvg 통합은 ``grid.py`` 의 ``submit_lora`` 가 이미 수행한다.
        여기서는 그 결과를 받아 status=COMPLETED 로 기록하고 PEER_BONUS 등을
        적립한다.
        """
        try:
            from hwarang_api.db import prisma  # type: ignore
        except Exception:
            prisma = None  # type: ignore[assignment]

        connected = prisma is not None and getattr(prisma, "is_connected", lambda: False)()

        # 참가자 조회
        participants: list[dict[str, Any]] = []
        if connected:
            try:
                rows = await prisma.roundparticipant.find_many(  # type: ignore[attr-defined]
                    where={"roundId": round_id},
                )
                for r in rows:
                    participants.append({
                        "agent_id": getattr(r, "agentId", None),
                        "status": getattr(r, "status", None),
                        "quality_score": getattr(r, "qualityScore", None),
                    })
            except Exception as e:
                logger.warning("complete_round 참가자 조회 실패: %s", e)

        # peer vote 기반 quality 평균 계산 (각 peer 별)
        quality_by_agent = await self._aggregate_peer_votes(round_id)

        # ----- AgentEarnings 기록 -----
        rewards: list[dict[str, Any]] = []
        if connected:
            for p in participants:
                aid = p.get("agent_id")
                status = p.get("status")
                if not aid or status != "SUBMITTED":
                    continue
                quality = quality_by_agent.get(aid, p.get("quality_score") or 0.5)
                # quality 기반 단순 보상 — 외부 reward_calculator 우선
                amount = 100.0 * float(quality) + 50.0

                try:
                    await prisma.agentearnings.create(  # type: ignore[attr-defined]
                        data={
                            "agentId": aid,
                            "roundId": round_id,
                            "amount": float(amount),
                            "source": "HFL_REWARD",
                            "metadata": {"quality_score": float(quality)},
                        }
                    )
                except Exception as e:
                    logger.warning("AgentEarnings.create 실패 (%s): %s", aid, e)

                # qualityScore 동기화
                try:
                    await prisma.roundparticipant.update_many(  # type: ignore[attr-defined]
                        where={"roundId": round_id, "agentId": aid},
                        data={"qualityScore": float(quality)},
                    )
                except Exception:
                    pass

                rewards.append({
                    "agent_id": aid,
                    "amount": amount,
                    "quality_score": quality,
                })

        # 외부 reward_calculator override
        if reward_calculator is not None:
            try:
                rewards = list(reward_calculator(participants) or [])
            except Exception as e:
                logger.warning("reward_calculator 실패(무시): %s", e)

        # ----- Round.status = COMPLETED -----
        if connected:
            try:
                await prisma.round.update(  # type: ignore[attr-defined]
                    where={"id": round_id},
                    data={
                        "status": "COMPLETED",
                        "completedAt": datetime.now(timezone.utc),
                    },
                )
            except Exception as e:
                logger.warning("Round.status=COMPLETED 갱신 실패: %s", e)

        # ----- 웹소켓 fanout -----
        if broadcast is not None:
            try:
                await broadcast(
                    "round_completed",
                    round_id,
                    None,
                    {
                        "merged_lora_path": merged_lora_path,
                        "new_lora_version": new_lora_version,
                        "rewards": rewards,
                    },
                    None,
                )
            except Exception as e:
                logger.warning("broadcast_round_event(complete) 실패: %s", e)

        return {
            "status": "completed",
            "round_id": round_id,
            "rewards": rewards,
            "merged_lora_path": merged_lora_path,
            "new_lora_version": new_lora_version,
            "completed_at": time.time(),
        }

    # ──────────────────────────────────────────────────────
    # 내부 헬퍼
    # ──────────────────────────────────────────────────────
    async def _create_round(
        self,
        domain: str,
        config: dict[str, Any],
        validation_fraction: float,
    ) -> str:
        """Round 레코드 생성. Prisma 가 없으면 timestamp 기반 ID."""
        try:
            from hwarang_api.db import prisma  # type: ignore
        except Exception:
            prisma = None  # type: ignore[assignment]

        if prisma is not None and getattr(prisma, "is_connected", lambda: False)():
            try:
                row = await prisma.round.create(  # type: ignore[attr-defined]
                    data={
                        "domain": domain,
                        "status": "OPEN",
                        "config": config,
                        "validationFraction": validation_fraction,
                    }
                )
                return row.id
            except Exception as e:
                logger.warning("Round.create 실패 → 인메모리 ID 사용: %s", e)

        return f"round_{int(time.time() * 1000)}"

    async def _invite_participants(
        self, round_id: str, agent_ids: list[str]
    ) -> None:
        try:
            from hwarang_api.db import prisma  # type: ignore
        except Exception:
            return
        if not getattr(prisma, "is_connected", lambda: False)():
            return

        for aid in agent_ids:
            try:
                await prisma.roundparticipant.upsert(  # type: ignore[attr-defined]
                    where={"roundId_agentId": {"roundId": round_id, "agentId": aid}},
                    data={
                        "create": {
                            "roundId": round_id,
                            "agentId": aid,
                            "status": "INVITED",
                        },
                        "update": {"status": "INVITED"},
                    },
                )
            except Exception as e:
                logger.warning("RoundParticipant.upsert 실패 (%s): %s", aid, e)

    async def _attach_shards(
        self,
        round_id: str,
        plan: DataShardingService.ShardPlan,
    ) -> None:
        """RoundParticipant.shardId 매핑."""
        try:
            from hwarang_api.db import prisma  # type: ignore
        except Exception:
            return
        if not getattr(prisma, "is_connected", lambda: False)():
            return

        for shard in plan.shards:
            agent_id = shard.get("agent_id")
            if not agent_id:
                continue
            try:
                # shard 의 DB 레코드 ID 조회 (sharder._persist_shards 가 이미 작성)
                db_shard = await prisma.datashard.find_first(  # type: ignore[attr-defined]
                    where={"roundId": round_id, "shardIdx": shard["shard_idx"]},
                )
                shard_db_id = getattr(db_shard, "id", None) if db_shard else None
                await prisma.roundparticipant.update_many(  # type: ignore[attr-defined]
                    where={"roundId": round_id, "agentId": agent_id},
                    data={"shardId": shard_db_id, "status": "ACCEPTED"},
                )
            except Exception as e:
                logger.debug("shard 매핑 실패(%s, 무시): %s", agent_id, e)

    async def _mark_round_running(self, round_id: str) -> None:
        try:
            from hwarang_api.db import prisma  # type: ignore
        except Exception:
            return
        if not getattr(prisma, "is_connected", lambda: False)():
            return
        try:
            await prisma.round.update(  # type: ignore[attr-defined]
                where={"id": round_id},
                data={
                    "status": "RUNNING",
                    "startedAt": datetime.now(timezone.utc),
                },
            )
        except Exception as e:
            logger.debug("Round.status=RUNNING 갱신 실패(무시): %s", e)

    async def _aggregate_peer_votes(self, round_id: str) -> dict[str, float]:
        """각 peer 가 받은 quality_score 평균."""
        try:
            from hwarang_api.db import prisma  # type: ignore
        except Exception:
            return {}
        if not getattr(prisma, "is_connected", lambda: False)():
            return {}

        try:
            votes = await prisma.peervote.find_many(where={"roundId": round_id})  # type: ignore[attr-defined]
        except Exception as e:
            logger.debug("peervote 조회 실패: %s", e)
            return {}

        sums: dict[str, float] = {}
        counts: dict[str, int] = {}
        for v in votes:
            peer = getattr(v, "peerId", None)
            qs = getattr(v, "qualityScore", None)
            if peer is None or qs is None:
                continue
            sums[peer] = sums.get(peer, 0.0) + float(qs)
            counts[peer] = counts.get(peer, 0) + 1

        return {p: (sums[p] / counts[p]) for p in sums if counts.get(p)}


__all__ = ["RoundOrchestrator"]
