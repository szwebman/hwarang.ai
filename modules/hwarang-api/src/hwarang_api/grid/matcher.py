"""AgentMatcher — 라운드 적합 에이전트 점수화 / 선정.

화랑 그리드의 라운드 분배 1단계.

기존 :mod:`hwarang_api.routers.grid` 의 ``start_round`` 는 활성 에이전트 중
``tier in ("standard","full")`` 만 통과시키고 그 안에서 가중치를 두지 않았다.
이 모듈은:

* 에이전트의 ``domain specialization`` 과 라운드 ``domain`` 을 매칭
* ``tier`` / ``reputation`` / ``vram`` / ``region`` 다중 가중치 합산
* 다른 라운드에 ACCEPTED/SUBMITTED 인 에이전트는 동시참여 한도로 제외

반환은 점수 내림차순 ``Candidate`` top-N.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# 도메인 인접도 표
#
# 1.0 = 완전 일치, 0.5~0.7 = 인접, 0.1 = 무관 (기본값).
# 대칭으로 처리한다 (key 하나만 정의해도 양방향 적용).
# ────────────────────────────────────────────────────────────────
_DOMAIN_ADJACENCY: dict[tuple[str, str], float] = {
    ("law", "tax"): 0.5,
    ("law", "contract"): 0.7,
    ("tax", "contract"): 0.4,
    ("medical", "pharma"): 0.7,
    ("medical", "biology"): 0.4,
    ("pharma", "biology"): 0.5,
    ("code", "devops"): 0.6,
    ("code", "math"): 0.3,
    ("devops", "security"): 0.5,
    ("code", "security"): 0.4,
    ("finance", "tax"): 0.5,
    ("finance", "law"): 0.3,
}


def _domain_score(agent_domains: Iterable[str], round_domain: str | None) -> float:
    """에이전트 도메인 ↔ 라운드 도메인 점수 계산.

    * round_domain 이 None/general → 모두 0.5 중립
    * 완전 일치 → 1.0
    * 인접 → 위 표 값 (0.3~0.7)
    * 그 외 → 0.1
    """
    if not round_domain or round_domain == "general":
        return 0.5
    if not agent_domains:
        return 0.1

    best = 0.1
    for d in agent_domains:
        if not d:
            continue
        if d == round_domain:
            return 1.0
        # 인접도 표 양방향 조회
        adj = _DOMAIN_ADJACENCY.get((d, round_domain)) or _DOMAIN_ADJACENCY.get((round_domain, d))
        if adj is not None and adj > best:
            best = adj
    return best


_TIER_SCORE = {"full": 1.0, "standard": 0.6, "lite": 0.3}


def _tier_score(tier: str | None) -> float:
    return _TIER_SCORE.get((tier or "lite").lower(), 0.3)


def _reputation_score(rep: float | None) -> float:
    if rep is None:
        return 0.5
    return max(0.0, min(1.0, float(rep)))


def _gpu_score(vram_gb: float | None) -> float:
    if not vram_gb:
        return 0.0
    return max(0.0, min(1.0, float(vram_gb) / 24.0))


def _region_score(agent_region: str | None, round_region: str | None) -> float:
    if not round_region:
        return 0.5  # round 가 region 무관이면 중립
    if not agent_region:
        return 0.3
    return 1.0 if agent_region == round_region else 0.2


# 가중치 (합 = 1.0)
_W_DOMAIN = 0.40
_W_TIER = 0.20
_W_REPUTATION = 0.20
_W_GPU = 0.10
_W_REGION = 0.10


class AgentMatcher:
    """라운드에 적합한 에이전트를 점수화/선택."""

    @dataclass
    class Candidate:
        agent_id: str
        score: float
        reasons: dict[str, float] = field(default_factory=dict)

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        adjacency: dict[tuple[str, str], float] | None = None,
    ) -> None:
        # 가중치를 외부에서 주입 가능 (실험용)
        w = weights or {}
        self.w_domain = float(w.get("domain", _W_DOMAIN))
        self.w_tier = float(w.get("tier", _W_TIER))
        self.w_reputation = float(w.get("reputation", _W_REPUTATION))
        self.w_gpu = float(w.get("gpu", _W_GPU))
        self.w_region = float(w.get("region", _W_REGION))
        self._adjacency = adjacency or _DOMAIN_ADJACENCY

    # ──────────────────────────────────────────────────────
    # 외부 호출용 단일 에이전트 점수
    # (grid.py 의 list_open_rounds 가 호출함)
    # ──────────────────────────────────────────────────────
    async def score(
        self,
        agent: dict[str, Any],
        round_info: dict[str, Any],
    ) -> float:
        """단일 에이전트 ↔ 단일 라운드 점수 (0~1)."""
        return self._score_one(agent, round_info)["score"]

    # ──────────────────────────────────────────────────────
    # 메인 진입점
    # ──────────────────────────────────────────────────────
    async def rank_candidates(
        self,
        round_domain: str,
        active_agents: list[dict[str, Any]],
        max_concurrent_per_agent: int = 1,
        target_count: int = 10,
        round_region: str | None = None,
    ) -> list["AgentMatcher.Candidate"]:
        """라운드용 후보 점수화/정렬/필터링.

        Parameters
        ----------
        round_domain
            라운드의 전문 도메인 (예: "law", "medical", "code", "general").
        active_agents
            heartbeat 기반 활성 에이전트 dict 리스트. 필수 키: ``agent_id``.
            선택: ``tier``, ``vram_gb``, ``region``, ``reputation``,
            ``domains`` (또는 ``specialization`` / ``expert_tags``).
            Prisma ``ContributorProfile`` 이 있으면 그쪽으로 보강한다.
        max_concurrent_per_agent
            동시참여 한도. 다른 라운드에 ACCEPTED/SUBMITTED 인 에이전트가
            이미 한도 이상이면 후보에서 제외.
        target_count
            반환할 상위 N.
        round_region
            라운드 region (없으면 region 가중치 중립).
        """
        if not active_agents:
            return []

        # 동시참여 제한 — Prisma 가 있으면 RoundParticipant 활용, 없으면 통과
        active_load = await self._fetch_active_load(
            [a.get("agent_id") for a in active_agents if a.get("agent_id")]
        )

        # ContributorProfile 보강 (있으면)
        profile_map = await self._fetch_contributor_profiles(
            [a.get("agent_id") for a in active_agents if a.get("agent_id")]
        )

        round_info = {"domain": round_domain, "region": round_region}

        candidates: list[AgentMatcher.Candidate] = []
        for agent in active_agents:
            agent_id = agent.get("agent_id")
            if not agent_id:
                continue

            # 동시참여 한도 체크
            current_load = active_load.get(agent_id, 0)
            if current_load >= max_concurrent_per_agent:
                logger.debug(
                    "skip %s: concurrent_load=%d >= %d",
                    agent_id, current_load, max_concurrent_per_agent,
                )
                continue

            # ContributorProfile 보강
            merged = dict(agent)
            profile = profile_map.get(agent_id)
            if profile is not None:
                if profile.get("reputation") is not None and "reputation" not in merged:
                    merged["reputation"] = profile["reputation"]
                tags = profile.get("expert_tags") or []
                if tags and not merged.get("domains"):
                    merged["domains"] = tags

            scored = self._score_one(merged, round_info)
            candidates.append(
                AgentMatcher.Candidate(
                    agent_id=agent_id,
                    score=scored["score"],
                    reasons=scored["reasons"],
                )
            )

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:target_count]

    # ──────────────────────────────────────────────────────
    # 내부 헬퍼
    # ──────────────────────────────────────────────────────
    def _score_one(
        self,
        agent: dict[str, Any],
        round_info: dict[str, Any],
    ) -> dict[str, Any]:
        """가중치 합산 점수 + 분해(reasons)."""
        # 도메인 — agent['domains'] 또는 ['specialization'] 또는 단일 'domain'
        agent_domains: list[str] = []
        if isinstance(agent.get("domains"), list):
            agent_domains = list(agent["domains"])
        elif isinstance(agent.get("expert_tags"), list):
            agent_domains = list(agent["expert_tags"])
        elif agent.get("specialization"):
            agent_domains = [str(agent["specialization"])]
        elif agent.get("domain"):
            agent_domains = [str(agent["domain"])]

        round_domain = round_info.get("domain")

        d = _domain_score(agent_domains, round_domain)
        t = _tier_score(agent.get("tier"))
        r = _reputation_score(agent.get("reputation"))
        g = _gpu_score(agent.get("vram_gb"))
        rg = _region_score(agent.get("region"), round_info.get("region"))

        score = (
            self.w_domain * d
            + self.w_tier * t
            + self.w_reputation * r
            + self.w_gpu * g
            + self.w_region * rg
        )

        return {
            "score": round(score, 4),
            "reasons": {
                "domain": round(d, 3),
                "tier": round(t, 3),
                "reputation": round(r, 3),
                "gpu": round(g, 3),
                "region": round(rg, 3),
            },
        }

    async def _fetch_active_load(self, agent_ids: list[str]) -> dict[str, int]:
        """각 agent_id 가 현재 ACCEPTED/SUBMITTED 상태로 잡혀있는 라운드 수.

        Prisma 가 없거나 미연결이면 빈 dict 반환 (= 한도 통과).
        """
        if not agent_ids:
            return {}
        try:
            from hwarang_api.db import prisma  # type: ignore
        except Exception:
            return {}

        if not getattr(prisma, "is_connected", lambda: False)():
            return {}

        try:
            rows = await prisma.roundparticipant.find_many(  # type: ignore[attr-defined]
                where={
                    "agentId": {"in": agent_ids},
                    "status": {"in": ["ACCEPTED", "SUBMITTED", "INVITED"]},
                },
            )
        except Exception as e:
            logger.debug("active_load fetch 실패(무시): %s", e)
            return {}

        load: dict[str, int] = {}
        for row in rows:
            aid = getattr(row, "agentId", None)
            if not aid:
                continue
            load[aid] = load.get(aid, 0) + 1
        return load

    async def _fetch_contributor_profiles(
        self, agent_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Prisma ContributorProfile 에서 reputation/expert_tags 보강.

        에이전트 ID 가 user_id 와 동일한 형태일 때만 매칭됨.
        없으면 빈 dict.
        """
        if not agent_ids:
            return {}
        try:
            from hwarang_api.db import prisma  # type: ignore
        except Exception:
            return {}
        if not getattr(prisma, "is_connected", lambda: False)():
            return {}

        try:
            rows = await prisma.contributorprofile.find_many(  # type: ignore[attr-defined]
                where={"userId": {"in": agent_ids}},
            )
        except Exception as e:
            logger.debug("contributor_profile fetch 실패(무시): %s", e)
            return {}

        out: dict[str, dict[str, Any]] = {}
        for row in rows:
            uid = getattr(row, "userId", None)
            if not uid:
                continue
            out[uid] = {
                "reputation": getattr(row, "reputation", None),
                "expert_tags": list(getattr(row, "expertTags", []) or []),
                "tier": getattr(row, "tier", None),
            }
        return out


__all__ = ["AgentMatcher"]
