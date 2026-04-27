"""Grid Coordinator API — 에이전트들이 호출하는 엔드포인트.

모든 path prefix: /api/grid

통합 방법 (hwarang-api main.py 예):
    from hwarang_grid.coordinator.routes import router as grid_router
    app.include_router(grid_router)

인증:
    - 에이전트: X-Agent-Id + X-Agent-Key 헤더
    - 어드민:   X-Api-Key 헤더 (서버 ENV HWARANG_ADMIN_KEY 와 비교)

graceful imports: fastapi / pydantic 은 서버 환경에 반드시 있다고 가정하되,
모듈 임포트 실패 시에도 round_manager 만큼은 단독 사용 가능해야 한다.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

# fastapi / pydantic 은 hwarang-api 서버에 포함되어 있으므로 HARD require.
# 개발 테스트에서 단독 import 가 필요하면 round_manager 만 사용하면 된다.
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .round_manager import Round, get_registry

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/grid", tags=["grid"])


# ──────────────────────────────────────────────────────────────────────
# 간이 에이전트 키 스토어 (실제 DB 교체 가능)
# ──────────────────────────────────────────────────────────────────────

_AGENT_KEYS: dict[str, str] = {}
_AGENT_PROFILES: dict[str, dict[str, Any]] = {}
_AGENT_HEARTBEATS: dict[str, dict[str, Any]] = {}
_AGENT_EARNINGS: dict[str, list[dict[str, Any]]] = {}


def register_agent_key(agent_id: str, api_key: str) -> None:
    """외부(agent 등록 flow)에서 키를 주입할 때 사용."""
    _AGENT_KEYS[agent_id] = api_key


def _verify_agent_key(agent_id: str, api_key: str) -> bool:
    """스토어가 비어있으면 개발 편의를 위해 통과(프로덕션에서는 False 로 전환)."""
    if not _AGENT_KEYS:
        return True
    return _AGENT_KEYS.get(agent_id) == api_key


# ──────────────────────────────────────────────────────────────────────
# 인증 Dependency
# ──────────────────────────────────────────────────────────────────────


async def require_agent_auth(
    x_agent_id: str = Header(..., alias="X-Agent-Id"),
    x_agent_key: str = Header(..., alias="X-Agent-Key"),
) -> dict[str, Any]:
    """에이전트 인증 — X-Agent-Id + X-Agent-Key 헤더."""
    if not _verify_agent_key(x_agent_id, x_agent_key):
        raise HTTPException(status_code=401, detail="invalid_agent_key")
    return {"agent_id": x_agent_id}


async def require_admin(
    x_api_key: str = Header(..., alias="X-Api-Key"),
) -> None:
    """어드민 키 검증 (환경변수 HWARANG_ADMIN_KEY)."""
    expected = os.getenv("HWARANG_ADMIN_KEY", "")
    if not expected or x_api_key != expected:
        raise HTTPException(status_code=401, detail="admin_key_invalid")


# ──────────────────────────────────────────────────────────────────────
# Pydantic 바디 모델
# ──────────────────────────────────────────────────────────────────────


class CreateRoundBody(BaseModel):
    domain: str
    round_name: str
    base_model: str
    data_source: str = "hlkm_filtered"
    filter_criteria: dict[str, Any] = Field(default_factory=dict)
    lora_r: int = 16
    lora_alpha: int = 32
    epochs: int = 3
    batch_size: int = 2
    min_tier_required: str = "SILVER"
    min_vram_gb: int = 16
    max_participants: int = 20
    min_participants: int = 3
    reward_pool: int = 10000
    duration_hours: int = 24


class SubmitBody(BaseModel):
    lora_url: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class PeerVoteBody(BaseModel):
    peer_agent_id: str
    score: float
    rationale: str | None = None


class DeclineBody(BaseModel):
    reason: str = "unspecified"


class CancelBody(BaseModel):
    reason: str = "unspecified"


class AgentProfileBody(BaseModel):
    primary_domains: list[str] = Field(default_factory=list)
    excluded_domains: list[str] = Field(default_factory=list)
    expertise_level: str = "general"
    owner_user_id: str | None = None
    owner_expert_credentials: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=lambda: ["ko"])
    active_hours: str | None = None
    min_data_quality_tier: str = "GENERAL_MEDIA"
    auto_participate: bool = True
    max_concurrent_rounds: int = 1


class HeartbeatBody(BaseModel):
    status: str = "idle"
    gpu: dict[str, Any] = Field(default_factory=dict)
    current_round: str | None = None
    version: str | None = None


class RegisterAgentBody(BaseModel):
    agent_id: str
    api_key: str
    tier: str = "SILVER"
    vram_gb: int = 0
    gpu_name: str = "unknown"


# ──────────────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────────────


def _round_to_public_dict(r: Round) -> dict[str, Any]:
    """외부에 노출하는 라운드 요약."""
    d = r.to_dict()
    # 민감한 샤드 URL 은 참가자에게만 개별 endpoint 로 전달
    d.pop("data_shards", None)
    return d


# ══════════════════════════════════════════════════════════════════════
# Round Management (ADMIN)
# ══════════════════════════════════════════════════════════════════════


@router.post("/rounds/create", summary="라운드 생성 (admin)")
async def create_round_endpoint(
    body: CreateRoundBody,
    admin: None = Depends(require_admin),
) -> dict[str, Any]:
    """어드민이 새 HFL 라운드를 생성한다."""
    reg = get_registry()
    round_id = await reg.create_round(
        domain=body.domain,
        round_name=body.round_name,
        base_model=body.base_model,
        data_source=body.data_source,
        filter_criteria=body.filter_criteria,
        lora_r=body.lora_r,
        lora_alpha=body.lora_alpha,
        epochs=body.epochs,
        batch_size=body.batch_size,
        min_tier_required=body.min_tier_required,
        min_vram_gb=body.min_vram_gb,
        max_participants=body.max_participants,
        min_participants=body.min_participants,
        reward_pool=body.reward_pool,
        duration_hours=body.duration_hours,
    )
    return {"status": "ok", "round_id": round_id}


@router.get("/rounds", summary="전체 라운드 목록 (admin)")
async def admin_list_all_rounds(
    status: str | None = None,
    admin: None = Depends(require_admin),
) -> dict[str, Any]:
    reg = get_registry()
    rounds = await reg.list_all(status_filter=status)
    return {"count": len(rounds), "rounds": [r.to_dict() for r in rounds]}


@router.post("/rounds/{round_id}/cancel", summary="라운드 취소 (admin)")
async def cancel_round(
    round_id: str,
    body: CancelBody,
    admin: None = Depends(require_admin),
) -> dict[str, Any]:
    reg = get_registry()
    rnd = await reg.get_round(round_id)
    if rnd is None:
        raise HTTPException(404, "round_not_found")
    await reg.cancel_round(round_id, body.reason)
    return {"status": "cancelled", "round_id": round_id, "reason": body.reason}


@router.post("/rounds/{round_id}/aggregate", summary="집계 트리거 (admin)")
async def trigger_aggregate(
    round_id: str,
    admin: None = Depends(require_admin),
) -> dict[str, Any]:
    """수동으로 집계를 시작. (최소 인원 충족 시)"""
    reg = get_registry()
    return await reg.start_aggregation(round_id)


@router.post("/rounds/{round_id}/complete", summary="라운드 완료 (admin)")
async def complete_round(
    round_id: str,
    body: dict[str, Any],
    admin: None = Depends(require_admin),
) -> dict[str, Any]:
    """FedAvg 결과 업로드 + 보상 분배."""
    reg = get_registry()
    path = body.get("aggregated_lora_path", "")
    if not path:
        raise HTTPException(400, "aggregated_lora_path_required")
    return await reg.complete_round(round_id, path)


@router.get("/rounds/{round_id}", summary="라운드 상세")
async def get_round_detail(round_id: str) -> dict[str, Any]:
    reg = get_registry()
    rnd = await reg.get_round(round_id)
    if rnd is None:
        raise HTTPException(404, "round_not_found")
    return _round_to_public_dict(rnd)


# ══════════════════════════════════════════════════════════════════════
# Round Discovery (agents)
# ══════════════════════════════════════════════════════════════════════


@router.get("/rounds/open", summary="참여 가능한 open 라운드 목록")
async def list_open_rounds(
    domain: str | None = None,
    min_tier: str | None = None,
    auth: dict[str, Any] = Depends(require_agent_auth),
) -> dict[str, Any]:
    reg = get_registry()
    domain_filter = [d.strip() for d in domain.split(",")] if domain else None
    rounds = await reg.list_open_rounds(domain_filter=domain_filter, min_tier=min_tier)
    return {
        "agent_id": auth["agent_id"],
        "count": len(rounds),
        "rounds": [_round_to_public_dict(r) for r in rounds],
    }


# ══════════════════════════════════════════════════════════════════════
# Participation
# ══════════════════════════════════════════════════════════════════════


@router.post("/rounds/{round_id}/join", summary="라운드 참여")
async def join_round(
    round_id: str,
    auth: dict[str, Any] = Depends(require_agent_auth),
) -> dict[str, Any]:
    reg = get_registry()
    rnd = await reg.get_round(round_id)
    if rnd is None:
        raise HTTPException(404, "round_not_found")
    ok = await reg.add_participant(round_id, auth["agent_id"])
    if not ok:
        raise HTTPException(409, "join_failed")
    # 해당 에이전트의 샤드 URL 반환 (있으면)
    shard_url = rnd.data_shards.get(auth["agent_id"])
    return {
        "status": "joined",
        "round_id": round_id,
        "shard_url": shard_url,
        "eval_shard_url": rnd.eval_shard_url,
    }


@router.post("/rounds/{round_id}/decline", summary="라운드 거절")
async def decline_round(
    round_id: str,
    body: DeclineBody,
    auth: dict[str, Any] = Depends(require_agent_auth),
) -> dict[str, Any]:
    reg = get_registry()
    await reg.record_decline(round_id, auth["agent_id"], body.reason)
    return {"status": "declined", "round_id": round_id}


# ══════════════════════════════════════════════════════════════════════
# Submission
# ══════════════════════════════════════════════════════════════════════


@router.post("/rounds/{round_id}/submit", summary="훈련 결과 제출")
async def submit_result(
    round_id: str,
    body: SubmitBody,
    auth: dict[str, Any] = Depends(require_agent_auth),
) -> dict[str, Any]:
    reg = get_registry()
    ok = await reg.submit_result(
        round_id=round_id,
        agent_id=auth["agent_id"],
        lora_url=body.lora_url,
        metrics=body.metrics,
    )
    if not ok:
        raise HTTPException(409, "submit_failed")
    return {"status": "submitted", "round_id": round_id}


# ══════════════════════════════════════════════════════════════════════
# Peer Voting
# ══════════════════════════════════════════════════════════════════════


@router.post("/rounds/{round_id}/peer-vote", summary="동료 평가 제출")
async def peer_vote(
    round_id: str,
    body: PeerVoteBody,
    auth: dict[str, Any] = Depends(require_agent_auth),
) -> dict[str, Any]:
    reg = get_registry()
    await reg.add_peer_vote(
        round_id=round_id,
        voter_id=auth["agent_id"],
        peer_id=body.peer_agent_id,
        score=body.score,
        rationale=body.rationale,
    )
    return {"status": "vote_recorded"}


@router.get(
    "/rounds/{round_id}/peer-lora/{peer_agent_id}",
    summary="peer LoRA 어댑터 URL 획득",
)
async def get_peer_lora(
    round_id: str,
    peer_agent_id: str,
    auth: dict[str, Any] = Depends(require_agent_auth),
) -> dict[str, Any]:
    """동료 평가용으로 peer 의 제출 LoRA 위치를 알려준다."""
    reg = get_registry()
    rnd = await reg.get_round(round_id)
    if rnd is None:
        raise HTTPException(404, "round_not_found")
    sub = rnd.submissions.get(peer_agent_id)
    if sub is None:
        raise HTTPException(404, "submission_not_found")
    return {
        "peer_agent_id": peer_agent_id,
        "lora_url": sub["lora_url"],
        "base_model": rnd.base_model,
        "eval_shard_url": rnd.eval_shard_url,
    }


# ══════════════════════════════════════════════════════════════════════
# Agent Profile / Heartbeat
# ══════════════════════════════════════════════════════════════════════


@router.post("/agents/register", summary="에이전트 등록 (신규)")
async def register_agent(body: RegisterAgentBody) -> dict[str, Any]:
    """신규 에이전트가 최초 등록. api_key 는 이후 헤더로 사용."""
    register_agent_key(body.agent_id, body.api_key)
    _AGENT_PROFILES[body.agent_id] = {
        "tier": body.tier,
        "vram_gb": body.vram_gb,
        "gpu_name": body.gpu_name,
    }
    return {"status": "registered", "agent_id": body.agent_id}


@router.post("/agents/{agent_id}/profile", summary="프로필 업데이트")
async def update_agent_profile(
    agent_id: str,
    body: AgentProfileBody,
    auth: dict[str, Any] = Depends(require_agent_auth),
) -> dict[str, Any]:
    if auth["agent_id"] != agent_id:
        raise HTTPException(403, "agent_id_mismatch")
    existing = _AGENT_PROFILES.get(agent_id, {})
    existing.update(body.model_dump() if hasattr(body, "model_dump") else dict(body))
    _AGENT_PROFILES[agent_id] = existing
    return {"status": "updated", "profile": existing}


@router.get("/agents/{agent_id}/profile", summary="프로필 조회")
async def get_agent_profile(
    agent_id: str,
    auth: dict[str, Any] = Depends(require_agent_auth),
) -> dict[str, Any]:
    if auth["agent_id"] != agent_id:
        raise HTTPException(403, "agent_id_mismatch")
    return _AGENT_PROFILES.get(agent_id, {})


@router.post("/agents/{agent_id}/heartbeat", summary="하트비트 수신")
async def heartbeat(
    agent_id: str,
    body: HeartbeatBody,
    auth: dict[str, Any] = Depends(require_agent_auth),
) -> dict[str, Any]:
    if auth["agent_id"] != agent_id:
        raise HTTPException(403, "agent_id_mismatch")
    _AGENT_HEARTBEATS[agent_id] = {
        **(body.model_dump() if hasattr(body, "model_dump") else dict(body)),
        "at": datetime.utcnow().isoformat(),
    }
    # 후속 명령 (간단 버전: 없음. 하나로도 hfl_master 와 공존)
    return {"status": "ok", "commands": []}


@router.get("/agents/{agent_id}/heartbeats", summary="최근 하트비트 (admin)")
async def list_heartbeat(
    agent_id: str,
    admin: None = Depends(require_admin),
) -> dict[str, Any]:
    return _AGENT_HEARTBEATS.get(agent_id, {})


# ══════════════════════════════════════════════════════════════════════
# Earnings
# ══════════════════════════════════════════════════════════════════════


@router.get("/agents/{agent_id}/earnings", summary="에이전트 누적 수익")
async def fetch_earnings(
    agent_id: str,
    since: datetime | None = None,
    auth: dict[str, Any] = Depends(require_agent_auth),
) -> dict[str, Any]:
    if auth["agent_id"] != agent_id:
        raise HTTPException(403, "agent_id_mismatch")
    # 기여 기반 계산: 완료된 라운드에서 rewards 합산
    reg = get_registry()
    total = 0
    items: list[dict[str, Any]] = []
    for r in reg.rounds.values():
        if r.status != "completed":
            continue
        if since and r.completed_at and r.completed_at < since:
            continue
        amt = r.rewards.get(agent_id, 0)
        if amt:
            total += amt
            items.append({
                "round_id": r.round_id,
                "round_name": r.round_name,
                "domain": r.domain,
                "reward": amt,
                "at": r.completed_at.isoformat() if r.completed_at else None,
            })
    # 추가 off-round 수익 (crawling/inference)
    for entry in _AGENT_EARNINGS.get(agent_id, []):
        if since:
            at = entry.get("at")
            if at and datetime.fromisoformat(at) < since:
                continue
        total += int(entry.get("amount", 0))
        items.append(entry)
    return {"agent_id": agent_id, "total_hwr": total, "items": items}


@router.post("/agents/{agent_id}/earnings", summary="수익 기록 추가 (admin)")
async def add_earning(
    agent_id: str,
    body: dict[str, Any],
    admin: None = Depends(require_admin),
) -> dict[str, Any]:
    entry = {
        "amount": int(body.get("amount", 0)),
        "source": body.get("source", "unknown"),
        "at": datetime.utcnow().isoformat(),
        "meta": body.get("meta", {}),
    }
    _AGENT_EARNINGS.setdefault(agent_id, []).append(entry)
    return {"status": "ok", "entry": entry}


# ══════════════════════════════════════════════════════════════════════
# Health
# ══════════════════════════════════════════════════════════════════════


@router.get("/health", summary="Coordinator 헬스")
async def health() -> dict[str, Any]:
    reg = get_registry()
    return {
        "status": "ok",
        "rounds_total": len(reg.rounds),
        "rounds_open": sum(1 for r in reg.rounds.values() if r.status == "open"),
        "rounds_training": sum(1 for r in reg.rounds.values() if r.status == "training"),
        "rounds_completed": sum(1 for r in reg.rounds.values() if r.status == "completed"),
    }


__all__ = [
    "router",
    "require_agent_auth",
    "require_admin",
    "register_agent_key",
]
