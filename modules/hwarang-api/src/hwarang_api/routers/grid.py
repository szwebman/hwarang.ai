"""Grid/HFL API 라우터

에이전트 등록, HFL 연합 학습, 리워드 지급 엔드포인트.
hfl_master.py의 기능을 API 서버에 통합.

엔드포인트:
  POST /grid/register          - 에이전트 등록
  POST /grid/heartbeat         - 하트비트 수신
  GET  /grid/status             - Grid 상태 조회
  POST /grid/hfl/round/start   - 학습 라운드 시작 (관리자)
  GET  /grid/hfl/round/task    - 학습 작업 조회
  POST /grid/hfl/submit        - LoRA 업로드
  GET  /grid/hfl/lora/latest   - 최신 LoRA 다운로드
  GET  /grid/hfl/lora/version  - LoRA 버전 조회
  POST /grid/rewards/emit      - 코인 리워드 지급
  GET  /grid/rewards/stats     - 리워드 통계
"""

from __future__ import annotations

import json
import logging
import os
import time
import hashlib
from pathlib import Path
from dataclasses import dataclass, field, asdict

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import FileResponse, JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/grid", tags=["Grid/HFL"])

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
            "download_url": "/grid/hfl/lora/latest",
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
            "download_url": "/grid/hfl/lora/latest",
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
                        "data_url": f"/grid/hfl/data/{_current_round['round_id']}",
                        "upload_url": f"/grid/hfl/submit/{_current_round['round_id']}",
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

@router.post("/hfl/round/start")
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


@router.get("/hfl/round/task/{agent_id}")
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
        "data_url": f"/grid/hfl/data/{_current_round['round_id']}",
        "upload_url": f"/grid/hfl/submit/{_current_round['round_id']}",
        "deadline": time.time() + 3600,
    }


@router.post("/hfl/submit/{round_id}")
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


@router.get("/hfl/lora/latest")
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


@router.get("/hfl/lora/version")
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
