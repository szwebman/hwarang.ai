"""라운드 생성/관리 — 마스터 쪽 핵심.

에이전트들이 참여할 HFL(연합 학습) 라운드를 여기서 오케스트레이션한다.
메모리 + 파일(JSON) 영속화를 기본으로 하되, Redis/Postgres 확장 가능하도록
인터페이스를 단순하게 유지한다.

책임:
    - 라운드 CRUD (open/training/aggregating/completed/cancelled)
    - 에이전트 참여 등록/거절
    - 훈련 결과 제출 수집
    - Peer vote 기록
    - FedAvg 집계 트리거 + 보상 계산

철학:
    에이전트는 참여자(PARTICIPANT)일 뿐 마스터가 된다. 라운드 정의·데이터
    샤드·집계·보상은 모두 마스터 권한. 에이전트는 참여/거절/제출/투표만 한다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# 상수 / 티어
# ────────────────────────────────────────────────────────────────────────────

TIER_ORDER: dict[str, int] = {
    "BRONZE": 1,
    "SILVER": 2,
    "GOLD": 3,
    "PLATINUM": 4,
    "DIAMOND": 5,
}

ROUND_STATUSES: tuple[str, ...] = (
    "open",
    "training",
    "aggregating",
    "completed",
    "cancelled",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


# ────────────────────────────────────────────────────────────────────────────
# Round dataclass
# ────────────────────────────────────────────────────────────────────────────


@dataclass
class Round:
    """HFL 라운드 1건의 전체 상태."""

    round_id: str
    round_name: str
    domain: str
    base_model: str
    data_source: str  # 'hlkm_filtered', 'custom'
    filter_criteria: dict[str, Any]
    lora_r: int = 16
    lora_alpha: int = 32
    epochs: int = 3
    batch_size: int = 2
    min_tier_required: str = "SILVER"
    min_vram_gb: int = 16
    max_participants: int = 20
    min_participants: int = 3
    reward_pool: int = 10000  # HWARANG 전체 풀
    status: str = "open"
    participants: list[str] = field(default_factory=list)
    declined_by: list[str] = field(default_factory=list)
    # agent_id -> {lora_url, metrics, submitted_at}
    submissions: dict[str, dict[str, Any]] = field(default_factory=dict)
    # [{voter_id, peer_id, score, rationale, at}]
    peer_votes: list[dict[str, Any]] = field(default_factory=list)
    # agent_id -> 최종 보상(HWR)
    rewards: dict[str, int] = field(default_factory=dict)
    aggregated_lora_path: str | None = None
    data_shards: dict[str, str] = field(default_factory=dict)  # agent_id -> shard_url
    eval_shard_url: str | None = None
    created_at: datetime = field(default_factory=_now)
    starts_at: datetime | None = None
    deadline: datetime | None = None
    completed_at: datetime | None = None
    cancel_reason: str | None = None

    # ── 직렬화 ──
    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["created_at"] = _iso(self.created_at)
        d["starts_at"] = _iso(self.starts_at)
        d["deadline"] = _iso(self.deadline)
        d["completed_at"] = _iso(self.completed_at)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Round":
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        known["created_at"] = _parse_iso(data.get("created_at")) or _now()
        known["starts_at"] = _parse_iso(data.get("starts_at"))
        known["deadline"] = _parse_iso(data.get("deadline"))
        known["completed_at"] = _parse_iso(data.get("completed_at"))
        return cls(**known)


# ────────────────────────────────────────────────────────────────────────────
# Registry
# ────────────────────────────────────────────────────────────────────────────


class RoundRegistry:
    """라운드 전역 관리. 메모리 + 파일 영속화."""

    def __init__(self, storage_path: str = "~/.hwarang/master/rounds.json"):
        self.rounds: dict[str, Round] = {}
        self.storage_path = Path(storage_path).expanduser()
        self._lock = asyncio.Lock()
        self._load()

    # ── 영속화 ──
    def _load(self) -> None:
        """JSON 파일에서 라운드 복원."""
        if not self.storage_path.exists():
            logger.info("저장 파일 없음, 신규 시작: %s", self.storage_path)
            return
        try:
            with self.storage_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for rid, rd in data.items():
                self.rounds[rid] = Round.from_dict(rd)
            logger.info("라운드 %d건 로드", len(self.rounds))
        except Exception as exc:
            logger.warning("라운드 로드 실패: %s", exc)

    def _save(self) -> None:
        """JSON 파일로 저장 (atomic write)."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.storage_path.with_suffix(".tmp")
        payload = {rid: r.to_dict() for rid, r in self.rounds.items()}
        try:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            tmp.replace(self.storage_path)
        except Exception as exc:
            logger.error("라운드 저장 실패: %s", exc)

    # ── 생성 ──
    async def create_round(
        self,
        domain: str,
        round_name: str,
        base_model: str,
        data_source: str = "hlkm_filtered",
        filter_criteria: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """새 라운드 생성. HLKM 샤드 준비는 호출자가 별도로 트리거."""
        async with self._lock:
            round_id = f"r_{uuid.uuid4().hex[:12]}"
            now = _now()
            deadline = now + timedelta(hours=kwargs.pop("duration_hours", 24))
            rnd = Round(
                round_id=round_id,
                round_name=round_name,
                domain=domain,
                base_model=base_model,
                data_source=data_source,
                filter_criteria=filter_criteria or {},
                deadline=deadline,
                **{k: v for k, v in kwargs.items() if k in Round.__dataclass_fields__},
            )
            self.rounds[round_id] = rnd
            self._save()
            logger.info(
                "라운드 생성: %s (domain=%s, tier>=%s, pool=%d HWR)",
                round_id, domain, rnd.min_tier_required, rnd.reward_pool,
            )
            return round_id

    async def get_round(self, round_id: str) -> Round | None:
        return self.rounds.get(round_id)

    async def list_open_rounds(
        self,
        domain_filter: list[str] | None = None,
        min_tier: str | None = None,
    ) -> list[Round]:
        """open 상태 라운드 중 도메인/티어 필터."""
        out: list[Round] = []
        min_tier_v = TIER_ORDER.get((min_tier or "").upper(), 0)
        for r in self.rounds.values():
            if r.status != "open":
                continue
            if domain_filter:
                if not any(r.domain.startswith(d) for d in domain_filter):
                    continue
            if min_tier_v:
                required = TIER_ORDER.get(r.min_tier_required.upper(), 0)
                if min_tier_v < required:
                    continue
            out.append(r)
        out.sort(key=lambda x: x.created_at, reverse=True)
        return out

    async def list_all(self, status_filter: str | None = None) -> list[Round]:
        """전체 라운드 (어드민 대시보드용)."""
        out = list(self.rounds.values())
        if status_filter:
            out = [r for r in out if r.status == status_filter]
        out.sort(key=lambda x: x.created_at, reverse=True)
        return out

    # ── 참여 ──
    async def add_participant(self, round_id: str, agent_id: str) -> bool:
        """참가자 등록. 상한 초과·상태 오류 시 False."""
        async with self._lock:
            rnd = self.rounds.get(round_id)
            if rnd is None:
                return False
            if rnd.status != "open":
                logger.info("라운드 %s not open (상태=%s)", round_id, rnd.status)
                return False
            if agent_id in rnd.participants:
                return True  # idempotent
            if len(rnd.participants) >= rnd.max_participants:
                logger.info("라운드 %s 정원 초과", round_id)
                return False
            rnd.participants.append(agent_id)
            # declined 에서 제거 (마음 바꾼 경우)
            if agent_id in rnd.declined_by:
                rnd.declined_by.remove(agent_id)
            # 정원 가득 차면 training 으로 전환
            if len(rnd.participants) >= rnd.max_participants:
                rnd.status = "training"
                rnd.starts_at = _now()
                logger.info("라운드 %s 정원 충족 → training", round_id)
            self._save()
            return True

    async def record_decline(
        self, round_id: str, agent_id: str, reason: str,
    ) -> None:
        """에이전트가 참여 거절한 경우 기록."""
        async with self._lock:
            rnd = self.rounds.get(round_id)
            if rnd is None:
                return
            if agent_id not in rnd.declined_by:
                rnd.declined_by.append(agent_id)
            logger.info("라운드 %s: %s 거절 (사유=%s)", round_id, agent_id, reason)
            self._save()

    # ── 제출 ──
    async def submit_result(
        self,
        round_id: str,
        agent_id: str,
        lora_url: str,
        metrics: dict[str, Any],
    ) -> bool:
        """훈련 결과 업로드. 자동으로 aggregating 진행 조건 검사."""
        async with self._lock:
            rnd = self.rounds.get(round_id)
            if rnd is None:
                return False
            if agent_id not in rnd.participants:
                logger.warning("라운드 %s: %s 미참여자 제출 시도", round_id, agent_id)
                return False
            if rnd.status not in ("open", "training"):
                logger.info("라운드 %s: 상태=%s, 제출 거부", round_id, rnd.status)
                return False
            rnd.submissions[agent_id] = {
                "lora_url": lora_url,
                "metrics": metrics,
                "submitted_at": _iso(_now()),
            }
            # 최소 인원 도달 + 모두 제출 시 aggregating 전환
            if (
                len(rnd.submissions) >= max(rnd.min_participants, 1)
                and len(rnd.submissions) >= len(rnd.participants)
            ):
                rnd.status = "aggregating"
                logger.info("라운드 %s: 전원 제출 → aggregating", round_id)
            self._save()
            return True

    # ── Peer Vote ──
    async def add_peer_vote(
        self,
        round_id: str,
        voter_id: str,
        peer_id: str,
        score: float,
        rationale: str | None = None,
    ) -> None:
        """동료 평가 기록. 자기 자신 투표 거부."""
        if voter_id == peer_id:
            logger.info("자기 자신 투표 거부: %s", voter_id)
            return
        score = max(0.0, min(1.0, float(score)))
        async with self._lock:
            rnd = self.rounds.get(round_id)
            if rnd is None:
                return
            rnd.peer_votes.append({
                "voter_id": voter_id,
                "peer_id": peer_id,
                "score": score,
                "rationale": rationale,
                "at": _iso(_now()),
            })
            self._save()

    def _peer_score(self, rnd: Round, agent_id: str) -> float:
        """한 에이전트가 받은 peer 투표 평균 (기본 0.7)."""
        scores = [v["score"] for v in rnd.peer_votes if v["peer_id"] == agent_id]
        if not scores:
            return 0.7
        return sum(scores) / len(scores)

    # ── 집계 ──
    async def start_aggregation(self, round_id: str) -> dict[str, Any]:
        """모든 submission 수집 후 FedAvg 트리거 지시서 생성.

        peer_votes 가중치를 반영한 에이전트별 weight 를 함께 반환하여
        실제 FedAvg 코드(hfl_master 등)가 사용할 수 있도록 한다.
        """
        async with self._lock:
            rnd = self.rounds.get(round_id)
            if rnd is None:
                return {"error": "not_found"}
            if rnd.status not in ("training", "aggregating"):
                return {"error": f"invalid_status:{rnd.status}"}
            if len(rnd.submissions) < rnd.min_participants:
                return {"error": "not_enough_submissions"}

            rnd.status = "aggregating"
            weights: dict[str, float] = {}
            for agent_id, sub in rnd.submissions.items():
                metric_loss = float(sub.get("metrics", {}).get("loss", 1.0) or 1.0)
                peer = self._peer_score(rnd, agent_id)
                # 낮은 loss + 높은 peer 점수 → 큰 가중치
                w = peer / max(metric_loss, 0.05)
                weights[agent_id] = w
            total = sum(weights.values()) or 1.0
            weights = {k: v / total for k, v in weights.items()}
            self._save()
            return {
                "round_id": round_id,
                "submissions": rnd.submissions,
                "weights": weights,
                "peer_votes_count": len(rnd.peer_votes),
            }

    async def complete_round(
        self, round_id: str, aggregated_lora_path: str,
    ) -> dict[str, Any]:
        """라운드 완료 처리 + 보상 계산."""
        async with self._lock:
            rnd = self.rounds.get(round_id)
            if rnd is None:
                return {"error": "not_found"}
            rnd.aggregated_lora_path = aggregated_lora_path
            rnd.status = "completed"
            rnd.completed_at = _now()
            # 보상 계산(락 바깥으로 빼기 위해 임시 복사)
            self._save()

        rewards = await self.compute_rewards(round_id)
        async with self._lock:
            rnd = self.rounds[round_id]
            rnd.rewards = rewards
            self._save()
        logger.info("라운드 %s 완료. 총 보상 분배: %d HWR", round_id, sum(rewards.values()))
        return {
            "round_id": round_id,
            "status": "completed",
            "aggregated_lora_path": aggregated_lora_path,
            "rewards": rewards,
        }

    async def compute_rewards(self, round_id: str) -> dict[str, int]:
        """기여도 × peer vote → 보상 분배.

        - 각 제출자에게 기본 쿼터 + peer-vote 보너스
        - 정답 근접(낮은 loss) 가산
        - 총합은 reward_pool 이하
        """
        rnd = self.rounds.get(round_id)
        if rnd is None or not rnd.submissions:
            return {}

        base_each = rnd.reward_pool // max(len(rnd.submissions) * 2, 1)
        raw: dict[str, float] = {}
        for agent_id, sub in rnd.submissions.items():
            loss = float(sub.get("metrics", {}).get("loss", 1.0) or 1.0)
            acc = float(sub.get("metrics", {}).get("accuracy", 0.5) or 0.5)
            peer = self._peer_score(rnd, agent_id)
            quality = (acc * 0.6) + (peer * 0.4) + (1.0 / max(loss, 0.1)) * 0.1
            raw[agent_id] = max(quality, 0.1)

        total = sum(raw.values()) or 1.0
        bonus_pool = rnd.reward_pool - base_each * len(rnd.submissions)
        rewards: dict[str, int] = {}
        for agent_id, q in raw.items():
            bonus = int(bonus_pool * (q / total))
            rewards[agent_id] = base_each + bonus
        # 정직한 반올림 잔액은 가장 기여 높은 에이전트에게
        residual = rnd.reward_pool - sum(rewards.values())
        if residual and rewards:
            top = max(rewards, key=lambda k: raw[k])
            rewards[top] += residual
        return rewards

    # ── 취소 ──
    async def cancel_round(self, round_id: str, reason: str) -> None:
        """라운드 취소. open/training 만 가능."""
        async with self._lock:
            rnd = self.rounds.get(round_id)
            if rnd is None:
                return
            if rnd.status in ("completed", "cancelled"):
                return
            rnd.status = "cancelled"
            rnd.cancel_reason = reason
            rnd.completed_at = _now()
            self._save()
            logger.info("라운드 %s 취소 (사유=%s)", round_id, reason)

    # ── 샤드 ──
    async def attach_shards(
        self,
        round_id: str,
        shards: dict[str, str],
        eval_shard_url: str | None = None,
    ) -> None:
        """data_shard_prep 결과를 라운드에 부착."""
        async with self._lock:
            rnd = self.rounds.get(round_id)
            if rnd is None:
                return
            rnd.data_shards = dict(shards)
            rnd.eval_shard_url = eval_shard_url
            self._save()


# ────────────────────────────────────────────────────────────────────────────
# 싱글톤
# ────────────────────────────────────────────────────────────────────────────


_registry: RoundRegistry | None = None


def get_registry() -> RoundRegistry:
    """전역 레지스트리 접근자 (lazy init)."""
    global _registry
    if _registry is None:
        _registry = RoundRegistry()
    return _registry


def reset_registry_for_test(path: str | None = None) -> RoundRegistry:
    """테스트용 레지스트리 재초기화."""
    global _registry
    _registry = RoundRegistry(storage_path=path or "~/.hwarang/master/rounds.json")
    return _registry
