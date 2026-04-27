"""Grid/HFL API 라우터

에이전트 등록, HFL 연합 학습, 리워드 지급 엔드포인트.
hfl_master.py의 기능을 API 서버에 통합.

모든 경로는 `/api/grid/*` 로 통일.

엔드포인트:
  POST /api/grid/register                    - 에이전트 등록
  POST /api/grid/heartbeat                   - 하트비트 수신
  GET  /api/grid/status                      - Grid 상태 조회
  POST /api/grid/rounds/start                - 학습 라운드 시작 (관리자)
  GET  /api/grid/rounds/task/{agent_id}      - 학습 작업 조회
  POST /api/grid/rounds/{round_id}/submit    - LoRA 업로드
  GET  /api/grid/lora/latest                 - 최신 LoRA 다운로드
  GET  /api/grid/lora/version                - LoRA 버전 조회
  GET  /api/grid/rounds/open                 - 참여 가능 라운드 목록
  GET  /api/grid/rounds/{round_id}/peer-lora/{peer_agent_id}
  GET  /api/grid/rounds/{round_id}/eval-shard
  POST /api/grid/rounds/{round_id}/peer-vote
  GET  /api/grid/rounds/{round_id}/participants
  GET  /api/grid/agents/{agent_id}/earnings  - 수익 내역
  WS   /api/grid/rounds/ws                   - 라운드 이벤트 push
  POST /api/grid/rewards/emit                - 코인 리워드 지급
  GET  /api/grid/rewards/stats               - 리워드 통계
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import hashlib
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Form,
    HTTPException,
    Depends,
    Header,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, JSONResponse

from hwarang_api.middleware.auth import verify_api_key

# 분산 학습 보조 모듈 (다른 그룹이 동시 작성 중) — 모듈이 아직 없을 때도
# grid.py 임포트 자체는 성공해야 한다.
try:  # pragma: no cover - 임포트 시점에만 평가
    from hwarang_api.grid.matcher import AgentMatcher  # type: ignore
except Exception:  # pragma: no cover
    AgentMatcher = None  # type: ignore[assignment]

try:  # pragma: no cover
    from hwarang_api.grid.sharder import DataShardingService  # type: ignore
except Exception:  # pragma: no cover
    DataShardingService = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/grid", tags=["Grid/HFL"])

# ════════════════════════════════════════════════════════════════
# 인메모리 상태 (프로덕션에서는 Redis/DB로 교체)
# ════════════════════════════════════════════════════════════════

_agents: dict[str, dict] = {}          # agent_id → 에이전트 정보
_users: dict[str, dict] = {}           # user_id → 유저 정보 (멀티에이전트)
_referrals: dict[str, str] = {}        # user_id → referrer_user_id
_current_round: dict | None = None
_round_history: list[dict] = []
_lora_version: int = 0
_lora_path: str | None = None
_benchmark_score: float = 0.0
_reward_history: list[dict] = []

REFERRAL_REWARD = 5000  # 추천인 보상 (HWR)
WELCOME_REWARD = 3000   # 신규 가입 보상 (HWR)

STORAGE_DIR = Path(os.getenv("HFL_STORAGE", "/mnt/nvme2/hwarang/hfl"))
LORA_INBOX = STORAGE_DIR / "inbox"
LORA_MERGED = STORAGE_DIR / "merged"

for d in [LORA_INBOX, LORA_MERGED]:
    d.mkdir(parents=True, exist_ok=True)


# ════════════════════════════════════════════════════════════════
# 에이전트 관리
# ════════════════════════════════════════════════════════════════

@router.post("/register")
async def register_agent(
    agent_id: str = Form(...),
    gpu_name: str = Form("unknown"),
    vram_gb: float = Form(0),
    tier: str = Form("lite"),
    user_id: str = Form(""),
    agent_name: str = Form(""),
    referral_code: str = Form(""),
):
    """에이전트 등록.

    한 유저가 여러 에이전트(PC)를 등록 가능.
    추천인 코드 입력 시 양쪽에 보상.
    """
    # 유저 등록/업데이트
    if user_id:
        if user_id not in _users:
            _users[user_id] = {
                "user_id": user_id,
                "agents": [],
                "total_reward": 0,
                "referral_code": hashlib.md5(user_id.encode()).hexdigest()[:8],
                "referral_count": 0,
                "joined_at": time.time(),
            }

            # 추천인 처리
            if referral_code:
                referrer = next(
                    (u for u in _users.values() if u["referral_code"] == referral_code),
                    None,
                )
                if referrer and referrer["user_id"] != user_id:
                    _referrals[user_id] = referrer["user_id"]
                    referrer["referral_count"] += 1
                    referrer["total_reward"] += REFERRAL_REWARD
                    _users[user_id]["total_reward"] += WELCOME_REWARD

                    _reward_history.append({
                        "agent_id": "system",
                        "user_id": referrer["user_id"],
                        "amount": REFERRAL_REWARD,
                        "reason": f"referral_{user_id}",
                        "timestamp": time.time(),
                    })
                    _reward_history.append({
                        "agent_id": "system",
                        "user_id": user_id,
                        "amount": WELCOME_REWARD,
                        "reason": "welcome_bonus",
                        "timestamp": time.time(),
                    })
                    logger.info(f"추천 보상: {referrer['user_id']} → {REFERRAL_REWARD} HWR, {user_id} → {WELCOME_REWARD} HWR")

        if agent_id not in _users[user_id]["agents"]:
            _users[user_id]["agents"].append(agent_id)

    _agents[agent_id] = {
        "agent_id": agent_id,
        "agent_name": agent_name or f"Agent-{agent_id[:8]}",
        "user_id": user_id,
        "gpu_name": gpu_name,
        "vram_gb": vram_gb,
        "tier": tier,
        "registered_at": time.time(),
        "last_heartbeat": time.time(),
        "status": "idle",
        "reputation": 0.5,
        "contributions": 0,
        "total_reward": 0,
    }

    logger.info(f"에이전트 등록: {agent_id} ({gpu_name}, {vram_gb}GB, {tier}, user={user_id})")

    return {
        "status": "registered",
        "agent_id": agent_id,
        "user_id": user_id,
        "referral_code": _users.get(user_id, {}).get("referral_code", ""),
        "current_lora": {
            "version": _lora_version,
            "download_url": "/api/grid/lora/latest",
        } if _lora_path else None,
    }


# ════════════════════════════════════════════════════════════════
# 멀티 에이전트 / 유저 대시보드
# ════════════════════════════════════════════════════════════════

@router.get("/user/{user_id}/dashboard")
async def user_dashboard(user_id: str):
    """유저의 멀티 에이전트 현황 대시보드."""
    user = _users.get(user_id)
    if not user:
        raise HTTPException(404, "유저 없음")

    # 유저의 모든 에이전트 정보
    user_agents = [_agents[aid] for aid in user["agents"] if aid in _agents]

    cutoff = time.time() - 60
    online = [a for a in user_agents if a["last_heartbeat"] > cutoff]
    offline = [a for a in user_agents if a["last_heartbeat"] <= cutoff]

    total_vram = sum(a["vram_gb"] for a in user_agents)
    total_reward = sum(a["total_reward"] for a in user_agents) + user.get("total_reward", 0)
    total_contributions = sum(a["contributions"] for a in user_agents)

    # 에이전트별 리워드 내역
    agent_ids = set(user["agents"])
    user_rewards = [r for r in _reward_history if r.get("agent_id") in agent_ids or r.get("user_id") == user_id]

    return {
        "user_id": user_id,
        "referral_code": user["referral_code"],
        "referral_count": user["referral_count"],
        "summary": {
            "total_agents": len(user_agents),
            "online": len(online),
            "offline": len(offline),
            "total_vram_gb": total_vram,
            "total_reward_hwr": round(total_reward, 2),
            "total_contributions": total_contributions,
        },
        "agents": [
            {
                "agent_id": a["agent_id"],
                "name": a["agent_name"],
                "gpu": a["gpu_name"],
                "vram_gb": a["vram_gb"],
                "tier": a["tier"],
                "status": a["status"],
                "online": a["last_heartbeat"] > cutoff,
                "reputation": round(a["reputation"], 2),
                "contributions": a["contributions"],
                "reward": a["total_reward"],
                "last_seen": a["last_heartbeat"],
            }
            for a in user_agents
        ],
        "recent_rewards": user_rewards[-20:],
    }


@router.get("/user/{user_id}/referrals")
async def user_referrals(user_id: str):
    """유저의 추천인 현황."""
    user = _users.get(user_id)
    if not user:
        raise HTTPException(404, "유저 없음")

    referred_users = [
        {
            "user_id": uid,
            "joined_at": _users[uid]["joined_at"],
            "agent_count": len(_users[uid]["agents"]),
            "total_reward": _users[uid]["total_reward"],
        }
        for uid, referrer_id in _referrals.items()
        if referrer_id == user_id and uid in _users
    ]

    return {
        "user_id": user_id,
        "referral_code": user["referral_code"],
        "referral_count": user["referral_count"],
        "referral_reward_total": user["referral_count"] * REFERRAL_REWARD,
        "referred_users": referred_users,
    }


@router.post("/user/{user_id}/agents/{agent_id}/rename")
async def rename_agent(user_id: str, agent_id: str, name: str = Form(...)):
    """에이전트 이름 변경."""
    agent = _agents.get(agent_id)
    if not agent or agent.get("user_id") != user_id:
        raise HTTPException(404, "에이전트 없음")
    agent["agent_name"] = name
    return {"status": "renamed", "agent_id": agent_id, "name": name}


@router.post("/heartbeat")
async def heartbeat(
    agent_id: str = Form(...),
    metrics: str = Form("{}"),
):
    """에이전트 하트비트."""
    if agent_id not in _agents:
        raise HTTPException(404, "등록되지 않은 에이전트")

    _agents[agent_id]["last_heartbeat"] = time.time()

    parsed = json.loads(metrics)
    _agents[agent_id]["status"] = parsed.get("status", "idle")

    # 에이전트 LoRA 버전 확인 → 업데이트 필요하면 명령
    commands = []
    agent_version = parsed.get("lora_version", 0)

    if _lora_path and _lora_version > agent_version:
        commands.append({
            "type": "update_lora",
            "version": _lora_version,
            "download_url": "/api/grid/lora/latest",
        })

    # 학습 작업 확인
    if _current_round and _current_round.get("status") == "training":
        if agent_id in _current_round.get("participants", []):
            submitted = [s["agent_id"] for s in _current_round.get("submissions", [])]
            if agent_id not in submitted:
                commands.append({
                    "type": "train",
                    "task": {
                        "round_id": _current_round["round_id"],
                        "task": "train_lora",
                        "config": _current_round.get("config", {}),
                        "data_url": f"/api/grid/rounds/{_current_round['round_id']}/data",
                        "upload_url": f"/api/grid/rounds/{_current_round['round_id']}/submit",
                    },
                })

    return {
        "status": "ok",
        "commands": commands,
        "current_round": {
            "round_id": _current_round["round_id"],
            "status": _current_round["status"],
        } if _current_round else None,
    }


@router.get("/status")
async def grid_status():
    """Grid 전체 상태."""
    cutoff = time.time() - 60
    active = [a for a in _agents.values() if a["last_heartbeat"] > cutoff]

    return {
        "total_agents": len(_agents),
        "active_agents": len(active),
        "agents_by_tier": {
            "lite": sum(1 for a in _agents.values() if a["tier"] == "lite"),
            "standard": sum(1 for a in _agents.values() if a["tier"] == "standard"),
            "full": sum(1 for a in _agents.values() if a["tier"] == "full"),
        },
        "total_vram_gb": sum(a["vram_gb"] for a in active),
        "current_lora_version": _lora_version,
        "current_benchmark": _benchmark_score,
        "completed_rounds": len(_round_history),
        "total_rewards_issued": sum(r.get("amount", 0) for r in _reward_history),
        "current_round": _current_round,
        "agents": list(_agents.values()),
    }


# ════════════════════════════════════════════════════════════════
# HFL 학습 라운드
# ════════════════════════════════════════════════════════════════

@router.post("/rounds/start")
async def start_round(
    lora_r: int = 16,
    lora_alpha: int = 32,
    learning_rate: float = 2e-4,
    steps_per_round: int = 100,
):
    """새 학습 라운드 시작 (관리자용)."""
    global _current_round

    if _current_round and _current_round["status"] in ("training", "collecting"):
        raise HTTPException(400, "진행 중인 라운드가 있습니다")

    cutoff = time.time() - 60
    active = [a for a in _agents.values() if a["last_heartbeat"] > cutoff]
    eligible = [a for a in active if a["tier"] in ("standard", "full")]

    if len(eligible) < 1:
        raise HTTPException(400, f"참가 가능 에이전트 없음 (활성: {len(active)})")

    round_number = len(_round_history) + 1
    round_id = f"round_{round_number}_{int(time.time())}"

    _current_round = {
        "round_id": round_id,
        "round_number": round_number,
        "status": "training",
        "config": {
            "lora_r": lora_r,
            "lora_alpha": lora_alpha,
            "learning_rate": learning_rate,
            "steps_per_round": steps_per_round,
        },
        "participants": [a["agent_id"] for a in eligible],
        "submissions": [],
        "started_at": time.time(),
    }

    logger.info(f"라운드 {round_number} 시작: {len(eligible)}개 에이전트")

    return {
        "status": "started",
        "round_id": round_id,
        "participants": len(eligible),
        "participant_ids": [a["agent_id"] for a in eligible],
    }


@router.get("/rounds/task/{agent_id}")
async def get_round_task(agent_id: str):
    """에이전트 학습 작업 조회."""
    if not _current_round:
        return {"task": None}

    if agent_id not in _current_round.get("participants", []):
        return {"task": None}

    if _current_round["status"] != "training":
        return {"task": None}

    submitted = [s["agent_id"] for s in _current_round.get("submissions", [])]
    if agent_id in submitted:
        return {"task": None, "message": "이미 제출했습니다"}

    return {
        "round_id": _current_round["round_id"],
        "task": "train_lora",
        "config": _current_round["config"],
        "data_url": f"/api/grid/rounds/{_current_round['round_id']}/data",
        "upload_url": f"/api/grid/rounds/{_current_round['round_id']}/submit",
        "deadline": time.time() + 3600,
    }


@router.post("/rounds/{round_id}/submit")
async def submit_lora(
    round_id: str,
    agent_id: str = Form(...),
    metadata: str = Form("{}"),
    lora_file: UploadFile = File(...),
):
    """에이전트가 학습한 LoRA 업로드."""
    global _current_round, _lora_version, _lora_path, _benchmark_score

    if not _current_round or _current_round["round_id"] != round_id:
        raise HTTPException(400, "유효하지 않은 라운드")

    # 이미 제출 확인
    submitted = [s["agent_id"] for s in _current_round["submissions"]]
    if agent_id in submitted:
        raise HTTPException(400, "이미 제출했습니다")

    # 파일 저장
    lora_data = await lora_file.read()
    file_hash = hashlib.sha256(lora_data).hexdigest()

    save_dir = LORA_INBOX / round_id / agent_id
    save_dir.mkdir(parents=True, exist_ok=True)
    (save_dir / "adapter_model.safetensors").write_bytes(lora_data)

    meta = json.loads(metadata)
    (save_dir / "metadata.json").write_text(json.dumps(meta, indent=2))

    # 검증
    size_mb = len(lora_data) / 1024 / 1024
    quality_score = 1.0
    verified = True
    issues = []

    if size_mb < 0.1:
        issues.append("파일 너무 작음")
        quality_score -= 0.5
    if meta.get("final_loss", 99) > 10:
        issues.append("loss 너무 높음")
        quality_score -= 0.3
    if file_hash in [s.get("file_hash") for s in _current_round["submissions"]]:
        issues.append("중복 해시")
        quality_score -= 0.8
        verified = False

    quality_score = max(0, min(1, quality_score))

    submission = {
        "agent_id": agent_id,
        "round_id": round_id,
        "lora_path": str(save_dir),
        "file_hash": file_hash,
        "file_size_mb": round(size_mb, 1),
        "training_loss": meta.get("final_loss", 0),
        "quality_score": quality_score,
        "verified": verified,
        "submitted_at": time.time(),
    }

    _current_round["submissions"].append(submission)

    logger.info(
        f"LoRA 수신: {agent_id} ({size_mb:.1f}MB, "
        f"{'✅' if verified else '❌'}, 품질:{quality_score:.2f})"
    )

    # 모든 참가자 제출 완료 → 통합 시작
    total_participants = len(_current_round["participants"])
    total_submissions = len(_current_round["submissions"])

    result = {
        "status": "submitted",
        "verified": verified,
        "quality_score": quality_score,
        "progress": f"{total_submissions}/{total_participants}",
    }

    if total_submissions >= total_participants:
        _current_round["status"] = "aggregating"
        logger.info(f"모든 제출 완료 → LoRA 통합 시작")

        # 통합 (FedAvg)
        valid = [s for s in _current_round["submissions"] if s["verified"]]

        if valid:
            merged_dir = LORA_MERGED / f"v{_lora_version + 1}"
            merged_dir.mkdir(parents=True, exist_ok=True)

            # 가중 평균 통합 시도
            try:
                import torch
                from safetensors.torch import load_file, save_file

                total_quality = sum(s["quality_score"] for s in valid)
                merged_state = {}

                for i, sub in enumerate(valid):
                    adapter_file = Path(sub["lora_path"]) / "adapter_model.safetensors"
                    if not adapter_file.exists():
                        continue

                    state = load_file(str(adapter_file))
                    w = sub["quality_score"] / total_quality

                    for key, tensor in state.items():
                        if key in merged_state:
                            merged_state[key] += tensor.float() * w
                        else:
                            merged_state[key] = tensor.float() * w

                # dtype 복원
                first_state = load_file(
                    str(Path(valid[0]["lora_path"]) / "adapter_model.safetensors")
                )
                for key in merged_state:
                    if key in first_state:
                        merged_state[key] = merged_state[key].to(first_state[key].dtype)

                save_file(merged_state, str(merged_dir / "adapter_model.safetensors"))

                # 설정 복사
                first_config = Path(valid[0]["lora_path"]) / "adapter_config.json"
                if first_config.exists():
                    import shutil
                    shutil.copy(first_config, merged_dir / "adapter_config.json")

                _lora_version += 1
                _lora_path = str(merged_dir)
                _benchmark_score = sum(s["quality_score"] for s in valid) / len(valid)

                logger.info(f"✅ LoRA v{_lora_version} 통합 완료 (벤치마크: {_benchmark_score:.2f})")

            except ImportError:
                # torch 없으면 첫 번째 것 사용
                import shutil
                shutil.copytree(valid[0]["lora_path"], str(merged_dir), dirs_exist_ok=True)
                _lora_version += 1
                _lora_path = str(merged_dir)
                logger.warning("torch 없음 → 첫 번째 LoRA 채택")

            _current_round["status"] = "completed"
            _current_round["completed_at"] = time.time()
            _round_history.append(_current_round)

            # 리워드 지급 기록
            for sub in valid:
                agent = _agents.get(sub["agent_id"])
                if agent:
                    weight = sub["quality_score"] / total_quality
                    reward = round(100 * weight + 50 * sub["quality_score"], 2)
                    agent["contributions"] += 1
                    agent["total_reward"] += reward
                    agent["reputation"] = min(1.0, agent["reputation"] + 0.02)

                    _reward_history.append({
                        "agent_id": sub["agent_id"],
                        "amount": reward,
                        "reason": f"hfl_round_{_current_round['round_number']}",
                        "quality_score": sub["quality_score"],
                        "timestamp": time.time(),
                    })

                    logger.info(f"💰 리워드: {sub['agent_id']} → {reward} HWR")

            result["aggregation"] = "completed"
            result["new_version"] = _lora_version

    return result


@router.get("/lora/latest")
async def download_latest_lora():
    """최신 통합 LoRA 다운로드."""
    if not _lora_path:
        raise HTTPException(404, "아직 통합된 LoRA가 없습니다")

    lora_file = Path(_lora_path) / "adapter_model.safetensors"
    if not lora_file.exists():
        raise HTTPException(404, "LoRA 파일 없음")

    return FileResponse(
        str(lora_file),
        filename="adapter_model.safetensors",
        headers={"X-LoRA-Version": str(_lora_version)},
    )


@router.get("/lora/version")
async def lora_version():
    """현재 LoRA 버전."""
    return {
        "version": _lora_version,
        "benchmark": _benchmark_score,
    }


# ════════════════════════════════════════════════════════════════
# 리워드
# ════════════════════════════════════════════════════════════════

@router.post("/rewards/emit")
async def emit_reward(
    agent_id: str = Form(...),
    amount: float = Form(...),
    reason: str = Form("manual"),
):
    """코인 리워드 수동 지급 (관리자용)."""
    agent = _agents.get(agent_id)
    if not agent:
        raise HTTPException(404, "에이전트 없음")

    agent["total_reward"] += amount

    record = {
        "agent_id": agent_id,
        "amount": amount,
        "reason": reason,
        "timestamp": time.time(),
        "tx_hash": hashlib.sha256(f"{agent_id}{amount}{time.time()}".encode()).hexdigest()[:16],
    }
    _reward_history.append(record)

    logger.info(f"💰 수동 리워드: {agent_id} → {amount} HWR ({reason})")

    return {
        "status": "emitted",
        "tx_hash": record["tx_hash"],
        "agent_total": agent["total_reward"],
    }


@router.get("/rewards/stats")
async def reward_stats():
    """리워드 통계."""
    return {
        "total_issued": sum(r["amount"] for r in _reward_history),
        "total_transactions": len(_reward_history),
        "by_agent": {
            agent_id: {
                "total_reward": agent["total_reward"],
                "contributions": agent["contributions"],
                "reputation": agent["reputation"],
            }
            for agent_id, agent in _agents.items()
            if agent["total_reward"] > 0
        },
        "recent": _reward_history[-20:],
    }


@router.get("/rewards/history/{agent_id}")
async def agent_reward_history(agent_id: str):
    """에이전트별 리워드 내역."""
    history = [r for r in _reward_history if r["agent_id"] == agent_id]
    return {
        "agent_id": agent_id,
        "total_reward": sum(r["amount"] for r in history),
        "history": history,
    }


# ════════════════════════════════════════════════════════════════
# 데이터 수집 (에이전트 → 마스터)
# ════════════════════════════════════════════════════════════════

_collected_data: list[dict] = []

DATA_STORAGE = STORAGE_DIR / "collected_data"
DATA_STORAGE.mkdir(parents=True, exist_ok=True)

REWARD_PER_ITEM = 0.5  # 수집 건당 보상 (HWR)

@router.post("/data/upload")
async def upload_collected_data(
    agent_id: str = Form(...),
    source: str = Form("unknown"),
    data_file: UploadFile = File(...),
):
    """에이전트가 수집한 데이터 업로드.

    뉴스, 법령, 코드 등 크롤링 데이터를 마스터가 수집.
    품질 검증 후 학습 데이터로 변환 + 코인 보상.
    """
    content = await data_file.read()

    # 저장
    save_dir = DATA_STORAGE / source / agent_id
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / data_file.filename
    save_path.write_bytes(content)

    # 건수 세기
    lines = content.decode("utf-8", errors="ignore").strip().split("\n")
    item_count = len([l for l in lines if l.strip()])

    # 품질 검증 (기본: 최소 길이 체크)
    valid_count = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            if len(json.dumps(item, ensure_ascii=False)) > 50:
                valid_count += 1
        except json.JSONDecodeError:
            continue

    # 보상 계산
    reward = valid_count * REWARD_PER_ITEM
    quality_bonus = 0

    # 고품질 보너스 (유효율 90% 이상이면 2배)
    if item_count > 0 and valid_count / item_count >= 0.9:
        quality_bonus = reward * 0.5
        reward += quality_bonus

    # 에이전트 리워드 적립
    agent = _agents.get(agent_id)
    if agent:
        agent["total_reward"] += reward
        agent["contributions"] += 1

    _reward_history.append({
        "agent_id": agent_id,
        "amount": reward,
        "reason": f"data_collection_{source}",
        "item_count": valid_count,
        "timestamp": time.time(),
    })

    _collected_data.append({
        "agent_id": agent_id,
        "source": source,
        "file": str(save_path),
        "total_items": item_count,
        "valid_items": valid_count,
        "reward": reward,
        "timestamp": time.time(),
    })

    logger.info(
        f"📥 데이터 수신: {agent_id} [{source}] "
        f"{valid_count}/{item_count}건 유효 → +{reward:.1f} HWR"
    )

    return {
        "status": "accepted",
        "total_items": item_count,
        "valid_items": valid_count,
        "reward": round(reward, 2),
        "quality_bonus": round(quality_bonus, 2),
    }


@router.get("/data/stats")
async def collected_data_stats():
    """수집 데이터 통계."""
    total_items = sum(d["valid_items"] for d in _collected_data)
    total_reward = sum(d["reward"] for d in _collected_data)
    by_source = {}
    for d in _collected_data:
        src = d["source"]
        if src not in by_source:
            by_source[src] = {"count": 0, "items": 0}
        by_source[src]["count"] += 1
        by_source[src]["items"] += d["valid_items"]

    return {
        "total_uploads": len(_collected_data),
        "total_items": total_items,
        "total_reward_issued": round(total_reward, 2),
        "by_source": by_source,
        "recent": _collected_data[-20:],
    }


# ════════════════════════════════════════════════════════════════
# v3.3: 분산 학습 / Peer 평가 / 수익 / WebSocket
# ════════════════════════════════════════════════════════════════
#
# 새로 추가된 엔드포인트는 모두 Bearer 토큰 인증을 사용 (verify_api_key).
# Prisma 모델: Round, RoundParticipant, PeerVote, AgentEarnings, DataShard.
# AgentMatcher / DataShardingService 가 사용 가능하면 활용, 없으면 안전 폴백.

# WebSocket 연결 풀: agent_id → [WebSocket]
_ws_connections: dict[str, list[WebSocket]] = {}


def _verify_ws_bearer(token: str | None) -> bool:
    """WebSocket 핸드셰이크용 가벼운 Bearer 검증.

    HTTP 라우트의 verify_api_key 와 동일한 정책 (hk- prefix).
    settings.require_auth=False 환경에서는 토큰 없어도 허용.
    """
    if not token:
        return False
    if token.startswith("Bearer "):
        token = token[7:]
    return token.startswith("hk-")


async def broadcast_round_event(
    event_type: str,
    round_id: str,
    domain: str | None = None,
    metadata: dict | None = None,
    target_agents: list[str] | None = None,
) -> None:
    """라운드 이벤트를 connected agents 한테 fanout.

    target_agents=None 이면 전체 broadcast,
    list 가 주어지면 해당 agent_id 들만.
    """
    payload = {
        "type": event_type,
        "round_id": round_id,
        "domain": domain,
        "metadata": metadata or {},
        "ts": time.time(),
    }
    targets = target_agents if target_agents is not None else list(_ws_connections.keys())

    for agent_id in targets:
        conns = _ws_connections.get(agent_id, [])
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception as e:
                logger.debug(f"WS send 실패 ({agent_id}): {e}")
                dead.append(ws)
        for ws in dead:
            try:
                conns.remove(ws)
            except ValueError:
                pass
        if not conns and agent_id in _ws_connections:
            _ws_connections.pop(agent_id, None)


@router.get("/rounds/open")
async def list_open_rounds(
    agent_id: str = Query(...),
    domain: str | None = Query(None),
    max_results: int = Query(20, ge=1, le=100),
    api_key: str | None = Depends(verify_api_key),
):
    """에이전트가 참여 가능한 OPEN 상태 라운드 목록.

    AgentMatcher 가 있으면 도메인·tier·평판 기반으로 매칭 점수 계산.
    """
    try:
        from hwarang_api.db import prisma
    except Exception:
        prisma = None  # type: ignore[assignment]

    rounds: list[dict[str, Any]] = []

    if prisma is not None and getattr(prisma, "is_connected", lambda: False)():
        try:
            where: dict[str, Any] = {"status": "OPEN"}
            if domain:
                where["domain"] = domain
            db_rounds = await prisma.round.find_many(  # type: ignore[attr-defined]
                where=where,
                take=max_results,
                order={"createdAt": "desc"},
            )
            for r in db_rounds:
                rounds.append({
                    "round_id": r.id,
                    "domain": r.domain,
                    "status": r.status,
                    "config": r.config,
                    "created_at": r.createdAt.isoformat() if r.createdAt else None,
                })
        except Exception as e:
            logger.warning(f"prisma.round.find_many 실패: {e}")

    # 폴백: 인메모리 _current_round
    if not rounds and _current_round and _current_round.get("status") in ("training", "collecting", "OPEN"):
        if not domain or _current_round.get("domain") == domain:
            rounds.append({
                "round_id": _current_round["round_id"],
                "domain": _current_round.get("domain"),
                "status": _current_round.get("status"),
                "config": _current_round.get("config", {}),
                "created_at": None,
            })

    # AgentMatcher 점수 매김
    if AgentMatcher is not None and rounds:
        try:
            matcher = AgentMatcher()
            agent = _agents.get(agent_id, {"agent_id": agent_id})
            scored = []
            for r in rounds:
                score = await matcher.score(agent, r) if asyncio.iscoroutinefunction(getattr(matcher, "score", None)) else 0.5  # type: ignore[arg-type]
                scored.append({**r, "match_score": score})
            scored.sort(key=lambda x: x.get("match_score", 0), reverse=True)
            rounds = scored
        except Exception as e:
            logger.debug(f"AgentMatcher 점수 매김 실패(무시): {e}")

    return {"agent_id": agent_id, "domain": domain, "rounds": rounds[:max_results]}


@router.get("/rounds/{round_id}/peer-lora/{peer_agent_id}")
async def download_peer_lora(
    round_id: str,
    peer_agent_id: str,
    api_key: str | None = Depends(verify_api_key),
):
    """다른 에이전트가 제출한 LoRA 다운로드 (peer 평가용)."""
    adapter_path = LORA_INBOX / round_id / peer_agent_id / "adapter_model.safetensors"
    if not adapter_path.exists():
        raise HTTPException(404, "peer LoRA 없음")

    return FileResponse(
        str(adapter_path),
        filename=f"{peer_agent_id}_adapter.safetensors",
        headers={
            "X-Round-Id": round_id,
            "X-Peer-Agent-Id": peer_agent_id,
        },
    )


@router.get("/rounds/{round_id}/eval-shard")
async def get_eval_shard(
    round_id: str,
    agent_id: str = Query(...),
    inline: bool = Query(False, description="True면 메타+samples 를 함께 반환"),
    api_key: str | None = Depends(verify_api_key),
):
    """peer 평가용 validation shard 메타데이터 (10~20%).

    DataShardingService 가 있으면 그쪽으로 위임. ``inline=true`` 면 디스크에
    저장된 ``eval.jsonl`` 의 실제 샘플도 함께 반환한다.
    """
    meta: dict[str, Any] | None = None
    if DataShardingService is not None:
        try:
            svc = DataShardingService()
            result = svc.get_validation_shard(round_id, agent_id)  # type: ignore[attr-defined]
            if asyncio.iscoroutine(result):
                result = await result
            meta = result
        except Exception as e:
            logger.warning(f"DataShardingService.get_validation_shard 실패: {e}")

    if meta is None:
        # 폴백: 인메모리 라운드 → 더미 메타데이터
        if not _current_round or _current_round.get("round_id") != round_id:
            raise HTTPException(404, "라운드 없음")
        meta = {
            "round_id": round_id,
            "agent_id": agent_id,
            "shard_kind": "validation",
            "validation_fraction": 0.15,
            "data_url": f"/api/grid/rounds/{round_id}/data?kind=validation",
            "sample_count": 0,
        }

    if inline and DataShardingService is not None:
        try:
            samples = DataShardingService.read_eval_shard(round_id)
            meta["samples"] = samples
            if not meta.get("sample_count"):
                meta["sample_count"] = len(samples)
        except Exception as e:
            logger.warning(f"read_eval_shard 실패: {e}")

    return meta


@router.post("/rounds/{round_id}/peer-vote")
async def submit_peer_vote(
    round_id: str,
    payload: dict,
    api_key: str | None = Depends(verify_api_key),
):
    """peer 평가 투표 제출.

    Body: {voter_id, peer_id, quality_score, rationale?}
    """
    voter_id = payload.get("voter_id")
    peer_id = payload.get("peer_id")
    quality_score = payload.get("quality_score")
    rationale = payload.get("rationale")

    if not voter_id or not peer_id or quality_score is None:
        raise HTTPException(400, "voter_id, peer_id, quality_score 필수")
    try:
        quality_score = float(quality_score)
    except (TypeError, ValueError):
        raise HTTPException(400, "quality_score 는 숫자여야 함")
    if not (0 <= quality_score <= 1):
        raise HTTPException(400, "quality_score 는 0~1 범위")

    try:
        from hwarang_api.db import prisma
    except Exception:
        prisma = None  # type: ignore[assignment]

    if prisma is not None and getattr(prisma, "is_connected", lambda: False)():
        try:
            vote = await prisma.peervote.upsert(  # type: ignore[attr-defined]
                where={
                    "roundId_voterId_peerId": {
                        "roundId": round_id,
                        "voterId": voter_id,
                        "peerId": peer_id,
                    }
                },
                data={
                    "create": {
                        "roundId": round_id,
                        "voterId": voter_id,
                        "peerId": peer_id,
                        "qualityScore": quality_score,
                        "rationale": rationale,
                    },
                    "update": {
                        "qualityScore": quality_score,
                        "rationale": rationale,
                    },
                },
            )
            return {"status": "recorded", "vote_id": vote.id}
        except Exception as e:
            logger.warning(f"prisma.peervote.upsert 실패: {e}")

    # 폴백: 인메모리
    if _current_round and _current_round.get("round_id") == round_id:
        votes = _current_round.setdefault("peer_votes", [])
        votes.append({
            "voter_id": voter_id,
            "peer_id": peer_id,
            "quality_score": quality_score,
            "rationale": rationale,
            "ts": time.time(),
        })
    return {"status": "recorded_inmem"}


@router.get("/rounds/{round_id}/participants")
async def list_round_participants(
    round_id: str,
    api_key: str | None = Depends(verify_api_key),
):
    """라운드 참가자 목록."""
    try:
        from hwarang_api.db import prisma
    except Exception:
        prisma = None  # type: ignore[assignment]

    if prisma is not None and getattr(prisma, "is_connected", lambda: False)():
        try:
            parts = await prisma.roundparticipant.find_many(  # type: ignore[attr-defined]
                where={"roundId": round_id},
                order={"joinedAt": "asc"},
            )
            return {
                "round_id": round_id,
                "participants": [
                    {
                        "agent_id": p.agentId,
                        "status": p.status,
                        "shard_id": p.shardId,
                        "joined_at": p.joinedAt.isoformat() if p.joinedAt else None,
                        "submitted_at": p.submittedAt.isoformat() if p.submittedAt else None,
                        "quality_score": p.qualityScore,
                    }
                    for p in parts
                ],
            }
        except Exception as e:
            logger.warning(f"prisma.roundparticipant.find_many 실패: {e}")

    # 폴백: 인메모리
    if _current_round and _current_round.get("round_id") == round_id:
        submitted_ids = {s["agent_id"] for s in _current_round.get("submissions", [])}
        return {
            "round_id": round_id,
            "participants": [
                {
                    "agent_id": aid,
                    "status": "SUBMITTED" if aid in submitted_ids else "ACCEPTED",
                    "shard_id": None,
                    "joined_at": None,
                    "submitted_at": None,
                    "quality_score": None,
                }
                for aid in _current_round.get("participants", [])
            ],
        }
    raise HTTPException(404, "라운드 없음")


@router.get("/agents/{agent_id}/earnings")
async def get_agent_earnings(
    agent_id: str,
    since: str | None = Query(None, description="ISO8601 시작 시각"),
    api_key: str | None = Depends(verify_api_key),
):
    """에이전트 수익 내역."""
    since_dt: datetime | None = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "since 는 ISO8601 형식")

    try:
        from hwarang_api.db import prisma
    except Exception:
        prisma = None  # type: ignore[assignment]

    if prisma is not None and getattr(prisma, "is_connected", lambda: False)():
        try:
            where: dict[str, Any] = {"agentId": agent_id}
            if since_dt:
                where["createdAt"] = {"gte": since_dt}
            rows = await prisma.agentearnings.find_many(  # type: ignore[attr-defined]
                where=where,
                order={"createdAt": "desc"},
            )
            total = sum(float(r.amount) for r in rows)
            return {
                "agent_id": agent_id,
                "since": since,
                "total": total,
                "earnings": [
                    {
                        "amount": float(r.amount),
                        "source": r.source,
                        "round_id": r.roundId,
                        "created_at": r.createdAt.isoformat() if r.createdAt else None,
                    }
                    for r in rows
                ],
            }
        except Exception as e:
            logger.warning(f"prisma.agentearnings.find_many 실패: {e}")

    # 폴백: _reward_history
    history = [r for r in _reward_history if r.get("agent_id") == agent_id]
    if since_dt:
        cutoff = since_dt.timestamp()
        history = [r for r in history if r.get("timestamp", 0) >= cutoff]
    return {
        "agent_id": agent_id,
        "since": since,
        "total": sum(r.get("amount", 0) for r in history),
        "earnings": [
            {
                "amount": r.get("amount", 0),
                "source": r.get("reason", "unknown"),
                "round_id": None,
                "created_at": datetime.fromtimestamp(r.get("timestamp", 0)).isoformat()
                    if r.get("timestamp") else None,
            }
            for r in history
        ],
    }


@router.websocket("/rounds/ws")
async def rounds_websocket(
    websocket: WebSocket,
    agent_id: str = Query(...),
    token: str | None = Query(None),
):
    """라운드 이벤트 push 채널.

    Connect: ws://.../api/grid/rounds/ws?agent_id=AGENT&token=Bearer%20hk-...
    또는 헤더 Authorization: Bearer hk-...

    서버 → 에이전트 메시지:
      {"type": "round_open"|"round_close"|"round_completed",
       "round_id": ..., "domain": ..., "metadata": {...}}
    """
    # 헤더 또는 query 에서 토큰 수집
    auth_header = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    bearer = auth_header or token

    require_auth = True
    try:
        require_auth = bool(websocket.app.state.settings.require_auth)
    except Exception:
        pass

    if require_auth and not _verify_ws_bearer(bearer):
        await websocket.close(code=1008)  # policy violation
        return

    await websocket.accept()
    _ws_connections.setdefault(agent_id, []).append(websocket)
    logger.info(f"WS connected: {agent_id} (총 {sum(len(v) for v in _ws_connections.values())}개)")

    try:
        # 환영 메시지 + 현재 라운드 상태
        await websocket.send_json({
            "type": "hello",
            "agent_id": agent_id,
            "current_round": {
                "round_id": _current_round["round_id"],
                "status": _current_round.get("status"),
            } if _current_round else None,
            "ts": time.time(),
        })

        # ping/pong 유지 — 클라이언트 메시지 받으면 echo
        while True:
            msg = await websocket.receive_text()
            try:
                data = json.loads(msg)
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong", "ts": time.time()})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        logger.info(f"WS disconnected: {agent_id}")
    except Exception as e:
        logger.warning(f"WS 오류 ({agent_id}): {e}")
    finally:
        conns = _ws_connections.get(agent_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns and agent_id in _ws_connections:
            _ws_connections.pop(agent_id, None)
