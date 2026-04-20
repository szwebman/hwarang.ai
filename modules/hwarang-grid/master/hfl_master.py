"""HFL 마스터 서버 - 연합 학습 조율

에이전트들이 학습한 LoRA를 수집 → 검증 → 통합 → 재배포.

전체 순환:
  1. 마스터가 학습 라운드 시작 (데이터 + 설정 배포)
  2. 에이전트가 로컬 GPU에서 LoRA 학습
  3. 에이전트가 학습된 LoRA를 마스터에 업로드
  4. 마스터가 수집된 LoRA를 검증 (품질/사기 체크)
  5. 마스터가 FedAvg로 LoRA 통합
  6. 벤치마크 검증 → 기존보다 좋으면 채택
  7. 새 LoRA를 모든 에이전트에 배포
  8. 코인 리워드 지급

사용법:
    # API 서버로 실행
    uvicorn hfl_master:app --host 0.0.0.0 --port 9090

    # 또는 직접
    python master/hfl_master.py --port 9090
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# 상태 모델
# ════════════════════════════════════════════════════════════════

class RoundStatus(str, Enum):
    WAITING = "waiting"       # 에이전트 참가 대기
    TRAINING = "training"     # 에이전트들이 학습 중
    COLLECTING = "collecting" # LoRA 수집 중
    AGGREGATING = "aggregating"  # 통합 중
    VALIDATING = "validating" # 벤치마크 검증 중
    DISTRIBUTING = "distributing"  # 배포 중
    COMPLETED = "completed"   # 완료
    FAILED = "failed"


@dataclass
class AgentInfo:
    agent_id: str
    gpu_name: str
    vram_gb: float
    tier: str  # lite, standard, full
    registered_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    status: str = "idle"  # idle, training, uploading
    reputation: float = 0.5
    total_contributions: int = 0


@dataclass
class LoRASubmission:
    agent_id: str
    round_id: str
    lora_path: str          # 서버에 저장된 경로
    file_hash: str          # SHA256
    file_size_bytes: int
    training_steps: int
    training_loss: float
    submitted_at: float = field(default_factory=time.time)
    verified: bool = False
    quality_score: float = 0.0


@dataclass
class TrainingRound:
    round_id: str
    round_number: int
    status: RoundStatus = RoundStatus.WAITING
    config: dict = field(default_factory=dict)
    participants: list[str] = field(default_factory=list)
    submissions: list[LoRASubmission] = field(default_factory=list)
    merged_lora_path: str | None = None
    benchmark_score: float | None = None
    previous_score: float | None = None
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None


# ════════════════════════════════════════════════════════════════
# HFL 마스터
# ════════════════════════════════════════════════════════════════

class HFLMaster:
    """HFL 연합 학습 마스터.

    에이전트 등록, 라운드 관리, LoRA 수집/검증/통합/배포.
    """

    def __init__(
        self,
        storage_dir: str = "/mnt/nvme2/hwarang/hfl",
        min_participants: int = 2,
        max_rounds: int = 100,
    ):
        self.storage_dir = Path(storage_dir)
        self.min_participants = min_participants
        self.max_rounds = max_rounds

        # 디렉토리 구조
        self.lora_inbox = self.storage_dir / "inbox"       # 에이전트가 올린 LoRA
        self.lora_merged = self.storage_dir / "merged"     # 통합된 LoRA
        self.lora_archive = self.storage_dir / "archive"   # 이전 버전
        self.data_dir = self.storage_dir / "data"          # 학습 데이터

        for d in [self.lora_inbox, self.lora_merged, self.lora_archive, self.data_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # 상태
        self.agents: dict[str, AgentInfo] = {}
        self.current_round: TrainingRound | None = None
        self.round_history: list[TrainingRound] = []
        self.current_lora_version: int = 0
        self.current_lora_path: str | None = None
        self.current_benchmark: float = 0.0

        logger.info(f"HFL 마스터 초기화: {storage_dir}")

    # ════════════════════════════════════════════════════════════
    # 에이전트 관리
    # ════════════════════════════════════════════════════════════

    def register_agent(self, agent_id: str, gpu_name: str,
                        vram_gb: float, tier: str) -> dict:
        """에이전트 등록."""
        agent = AgentInfo(
            agent_id=agent_id,
            gpu_name=gpu_name,
            vram_gb=vram_gb,
            tier=tier,
        )
        self.agents[agent_id] = agent
        logger.info(f"에이전트 등록: {agent_id} ({gpu_name}, {vram_gb}GB, {tier})")

        return {
            "status": "registered",
            "agent_id": agent_id,
            "current_round": self._round_summary(),
            "current_lora": {
                "version": self.current_lora_version,
                "download_url": f"/hfl/lora/latest",
            } if self.current_lora_path else None,
        }

    def heartbeat(self, agent_id: str, metrics: dict) -> dict:
        """에이전트 하트비트 수신."""
        agent = self.agents.get(agent_id)
        if not agent:
            return {"error": "등록되지 않은 에이전트"}

        agent.last_heartbeat = time.time()
        agent.status = metrics.get("status", "idle")

        return {
            "status": "ok",
            "current_round": self._round_summary(),
            "commands": self._pending_commands(agent_id),
        }

    def get_active_agents(self) -> list[AgentInfo]:
        """활성 에이전트 (60초 이내 하트비트)."""
        cutoff = time.time() - 60
        return [a for a in self.agents.values() if a.last_heartbeat > cutoff]

    # ════════════════════════════════════════════════════════════
    # 학습 라운드 관리
    # ════════════════════════════════════════════════════════════

    def start_round(self, training_config: dict = None) -> dict:
        """새 학습 라운드 시작."""
        if self.current_round and self.current_round.status not in (
            RoundStatus.COMPLETED, RoundStatus.FAILED
        ):
            return {"error": "진행 중인 라운드가 있습니다"}

        active = self.get_active_agents()
        eligible = [a for a in active if a.tier in ("standard", "full")]

        if len(eligible) < self.min_participants:
            return {
                "error": f"참가 가능 에이전트 부족: {len(eligible)}/{self.min_participants}",
                "eligible_agents": len(eligible),
            }

        round_number = len(self.round_history) + 1
        round_id = f"round_{round_number}_{int(time.time())}"

        config = training_config or {
            "base_model": "qwen2.5-32b",
            "lora_r": 16,
            "lora_alpha": 32,
            "learning_rate": 2e-4,
            "steps_per_round": 100,
            "max_seq_length": 2048,
        }

        self.current_round = TrainingRound(
            round_id=round_id,
            round_number=round_number,
            status=RoundStatus.TRAINING,
            config=config,
            participants=[a.agent_id for a in eligible],
        )

        logger.info(f"라운드 {round_number} 시작: {len(eligible)}개 에이전트 참여")
        logger.info(f"  참가자: {[a.agent_id for a in eligible]}")

        return {
            "status": "started",
            "round_id": round_id,
            "round_number": round_number,
            "participants": len(eligible),
            "config": config,
        }

    def get_round_task(self, agent_id: str) -> dict | None:
        """에이전트에게 학습 작업 할당."""
        if not self.current_round:
            return None
        if agent_id not in self.current_round.participants:
            return None
        if self.current_round.status != RoundStatus.TRAINING:
            return None

        return {
            "round_id": self.current_round.round_id,
            "task": "train_lora",
            "config": self.current_round.config,
            "data_url": f"/hfl/data/{self.current_round.round_id}",
            "upload_url": f"/hfl/submit/{self.current_round.round_id}",
            "deadline": time.time() + 3600,  # 1시간 내 완료
        }

    # ════════════════════════════════════════════════════════════
    # LoRA 수집 & 검증
    # ════════════════════════════════════════════════════════════

    def submit_lora(self, agent_id: str, round_id: str,
                     lora_data: bytes, metadata: dict) -> dict:
        """에이전트가 학습한 LoRA 업로드."""
        if not self.current_round or self.current_round.round_id != round_id:
            return {"error": "유효하지 않은 라운드"}

        if agent_id not in self.current_round.participants:
            return {"error": "참가자가 아닙니다"}

        # 이미 제출했는지 확인
        existing = [s for s in self.current_round.submissions if s.agent_id == agent_id]
        if existing:
            return {"error": "이미 제출했습니다"}

        # 파일 저장
        file_hash = hashlib.sha256(lora_data).hexdigest()
        save_dir = self.lora_inbox / round_id / agent_id
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / "adapter_model.safetensors"
        save_path.write_bytes(lora_data)

        # 메타데이터 저장
        (save_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

        # 검증
        verification = self._verify_submission(lora_data, metadata, agent_id)

        submission = LoRASubmission(
            agent_id=agent_id,
            round_id=round_id,
            lora_path=str(save_dir),
            file_hash=file_hash,
            file_size_bytes=len(lora_data),
            training_steps=metadata.get("training_steps", 0),
            training_loss=metadata.get("final_loss", 99.0),
            verified=verification["passed"],
            quality_score=verification["quality_score"],
        )

        self.current_round.submissions.append(submission)

        logger.info(
            f"LoRA 수신: {agent_id} "
            f"(크기: {len(lora_data)/1024/1024:.1f}MB, "
            f"loss: {submission.training_loss:.4f}, "
            f"검증: {'✅' if verification['passed'] else '❌'})"
        )

        # 모든 참가자가 제출했으면 → 통합 시작
        submitted = len(self.current_round.submissions)
        total = len(self.current_round.participants)

        result = {
            "status": "submitted",
            "verified": verification["passed"],
            "quality_score": verification["quality_score"],
            "progress": f"{submitted}/{total}",
        }

        if submitted >= total or submitted >= self.min_participants:
            self._start_aggregation()
            result["aggregation"] = "started"

        return result

    def _verify_submission(self, lora_data: bytes, metadata: dict,
                            agent_id: str) -> dict:
        """LoRA 제출물 검증."""
        issues = []
        score = 1.0

        # 1. 크기 검증 (너무 작거나 큰 LoRA 의심)
        size_mb = len(lora_data) / 1024 / 1024
        if size_mb < 0.1:
            issues.append("LoRA가 너무 작음 (빈 파일?)")
            score -= 0.5
        if size_mb > 500:
            issues.append("LoRA가 비정상적으로 큼")
            score -= 0.3

        # 2. 학습 loss 검증
        loss = metadata.get("final_loss", 99)
        if loss > 10:
            issues.append("loss가 비정상적으로 높음 (학습 실패?)")
            score -= 0.3
        if loss < 0.001:
            issues.append("loss가 비정상적으로 낮음 (오버피팅/사기?)")
            score -= 0.4

        # 3. 학습 스텝 수 검증
        steps = metadata.get("training_steps", 0)
        if steps < 10:
            issues.append("학습 스텝이 너무 적음")
            score -= 0.3

        # 4. 해시 중복 검증 (같은 LoRA 재제출 방지)
        file_hash = hashlib.sha256(lora_data).hexdigest()
        for prev in self.current_round.submissions:
            if prev.file_hash == file_hash and prev.agent_id != agent_id:
                issues.append("다른 에이전트와 동일한 LoRA (복사 의심)")
                score -= 0.8

        # 5. 에이전트 평판 반영
        agent = self.agents.get(agent_id)
        if agent and agent.reputation < 0.3:
            score -= 0.2

        passed = score >= 0.5 and len([i for i in issues if "사기" in i or "복사" in i]) == 0

        if issues:
            logger.warning(f"검증 이슈 ({agent_id}): {issues}")

        return {
            "passed": passed,
            "quality_score": max(0, min(1, score)),
            "issues": issues,
        }

    # ════════════════════════════════════════════════════════════
    # LoRA 통합 (FedAvg / TIES)
    # ════════════════════════════════════════════════════════════

    def _start_aggregation(self):
        """검증된 LoRA를 통합."""
        if not self.current_round:
            return

        self.current_round.status = RoundStatus.AGGREGATING

        # 검증 통과한 제출물만
        valid = [s for s in self.current_round.submissions if s.verified]

        if len(valid) < self.min_participants:
            logger.warning(f"검증 통과 LoRA 부족: {len(valid)}/{self.min_participants}")
            self.current_round.status = RoundStatus.FAILED
            return

        logger.info(f"LoRA 통합 시작: {len(valid)}개 제출물")

        # 품질 기반 가중 평균
        total_quality = sum(s.quality_score for s in valid)
        weights = {s.agent_id: s.quality_score / total_quality for s in valid}

        lora_paths = [s.lora_path for s in valid]

        try:
            merged_path = self._merge_loras(lora_paths, weights)
            self.current_round.merged_lora_path = merged_path
            self.current_round.status = RoundStatus.VALIDATING

            # 벤치마크 검증
            benchmark = self._run_benchmark(merged_path)
            self.current_round.benchmark_score = benchmark
            self.current_round.previous_score = self.current_benchmark

            if benchmark > self.current_benchmark:
                # 기존보다 나음 → 채택!
                self._adopt_new_lora(merged_path, benchmark)
                self.current_round.status = RoundStatus.DISTRIBUTING
                self._distribute_to_agents()
                self.current_round.status = RoundStatus.COMPLETED
                self._reward_participants(valid, weights)

                logger.info(
                    f"✅ 라운드 {self.current_round.round_number} 성공! "
                    f"벤치마크: {self.current_benchmark:.2f} → {benchmark:.2f}"
                )
            else:
                logger.info(
                    f"⚠️ 라운드 {self.current_round.round_number}: "
                    f"기존({self.current_benchmark:.2f}) ≥ 신규({benchmark:.2f}), 폐기"
                )
                self.current_round.status = RoundStatus.FAILED

        except Exception as e:
            logger.error(f"통합 실패: {e}")
            self.current_round.status = RoundStatus.FAILED

        self.current_round.completed_at = time.time()
        self.round_history.append(self.current_round)

    def _merge_loras(self, lora_paths: list[str],
                      weights: dict[str, float]) -> str:
        """여러 LoRA를 가중 평균으로 합성.

        실제로는 safetensors 파일의 텐서를 로드해서
        가중 평균을 계산합니다.
        """
        output_dir = self.lora_merged / f"v{self.current_lora_version + 1}"
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            import torch
            from safetensors.torch import load_file, save_file

            # 각 LoRA의 가중치 로드
            all_weights = {}
            for path in lora_paths:
                adapter_file = Path(path) / "adapter_model.safetensors"
                if adapter_file.exists():
                    state_dict = load_file(str(adapter_file))
                    agent_id = Path(path).name
                    w = weights.get(agent_id, 1.0 / len(lora_paths))
                    all_weights[agent_id] = (state_dict, w)

            if not all_weights:
                raise ValueError("로드 가능한 LoRA가 없습니다")

            # 가중 평균 (FedAvg)
            merged_state = {}
            first_agent = list(all_weights.keys())[0]
            first_state = all_weights[first_agent][0]

            for key in first_state.keys():
                weighted_sum = torch.zeros_like(first_state[key], dtype=torch.float32)
                for agent_id, (state, w) in all_weights.items():
                    if key in state:
                        weighted_sum += state[key].float() * w
                merged_state[key] = weighted_sum.to(first_state[key].dtype)

            # 저장
            save_file(merged_state, str(output_dir / "adapter_model.safetensors"))

            # adapter_config.json 복사 (첫 번째 것 사용)
            first_config = Path(lora_paths[0]) / "adapter_config.json"
            if first_config.exists():
                shutil.copy(first_config, output_dir / "adapter_config.json")

            logger.info(f"LoRA 통합 완료: {output_dir}")
            return str(output_dir)

        except ImportError:
            # torch 없으면 단순 복사 (테스트용)
            logger.warning("torch 없음 → 첫 번째 LoRA를 그대로 사용")
            shutil.copytree(lora_paths[0], str(output_dir), dirs_exist_ok=True)
            return str(output_dir)

    def _run_benchmark(self, lora_path: str) -> float:
        """통합된 LoRA 품질 벤치마크."""
        # 실제로는 테스트 세트로 perplexity / 정확도 측정
        # 여기서는 제출물의 평균 점수로 대체
        if not self.current_round:
            return 0.0

        valid = [s for s in self.current_round.submissions if s.verified]
        if not valid:
            return 0.0

        avg_quality = sum(s.quality_score for s in valid) / len(valid)
        avg_loss = sum(s.training_loss for s in valid) / len(valid)

        # loss가 낮고 quality가 높을수록 좋은 점수
        score = avg_quality * (1.0 / max(avg_loss, 0.1))
        return min(score, 10.0)

    def _adopt_new_lora(self, merged_path: str, benchmark: float):
        """새 LoRA를 현재 모델로 채택."""
        # 기존 버전 아카이브
        if self.current_lora_path:
            archive_name = f"v{self.current_lora_version}_{int(time.time())}"
            archive_dest = self.lora_archive / archive_name
            if Path(self.current_lora_path).exists():
                shutil.move(self.current_lora_path, str(archive_dest))

        self.current_lora_version += 1
        self.current_lora_path = merged_path
        self.current_benchmark = benchmark

        logger.info(f"새 LoRA 채택: v{self.current_lora_version} (벤치마크: {benchmark:.2f})")

    def _distribute_to_agents(self):
        """새 LoRA를 모든 활성 에이전트에 알림.

        실제 다운로드는 에이전트가 /hfl/lora/latest 엔드포인트에서
        pull 방식으로 가져감.
        """
        active = self.get_active_agents()
        logger.info(f"새 LoRA v{self.current_lora_version} 배포 알림: {len(active)}개 에이전트")

        # 에이전트들에게 "새 버전 있음" 알림
        # (하트비트 응답에 포함되어 자동 전파됨)

    def _reward_participants(self, submissions: list[LoRASubmission],
                              weights: dict[str, float]):
        """참여 에이전트에 코인 리워드."""
        base_reward = 100  # 기본 보상 (HWR)

        for sub in submissions:
            agent = self.agents.get(sub.agent_id)
            if not agent:
                continue

            # 기여도 기반 보상
            contribution_weight = weights.get(sub.agent_id, 0)
            quality_bonus = sub.quality_score * 50
            reward = base_reward * contribution_weight + quality_bonus

            agent.total_contributions += 1
            agent.reputation = min(1.0, agent.reputation + 0.02)

            logger.info(
                f"리워드: {sub.agent_id} → {reward:.1f} HWR "
                f"(기여도: {contribution_weight:.2f}, 품질: {sub.quality_score:.2f})"
            )

    # ════════════════════════════════════════════════════════════
    # 유틸리티
    # ════════════════════════════════════════════════════════════

    def _round_summary(self) -> dict | None:
        if not self.current_round:
            return None
        return {
            "round_id": self.current_round.round_id,
            "round_number": self.current_round.round_number,
            "status": self.current_round.status.value,
            "participants": len(self.current_round.participants),
            "submissions": len(self.current_round.submissions),
        }

    def _pending_commands(self, agent_id: str) -> list[dict]:
        """에이전트에게 전달할 명령."""
        commands = []

        # 새 LoRA 버전이 있으면 업데이트 명령
        # (에이전트가 현재 버전을 하트비트에 포함해서 비교)
        if self.current_lora_path:
            commands.append({
                "type": "update_lora",
                "version": self.current_lora_version,
                "download_url": "/hfl/lora/latest",
            })

        # 학습 작업이 있으면
        task = self.get_round_task(agent_id)
        if task:
            commands.append({
                "type": "train",
                "task": task,
            })

        return commands

    def get_status(self) -> dict:
        """전체 시스템 상태."""
        return {
            "active_agents": len(self.get_active_agents()),
            "total_agents": len(self.agents),
            "current_lora_version": self.current_lora_version,
            "current_benchmark": self.current_benchmark,
            "current_round": self._round_summary(),
            "completed_rounds": len(self.round_history),
            "agents": [
                {
                    "id": a.agent_id,
                    "gpu": a.gpu_name,
                    "tier": a.tier,
                    "status": a.status,
                    "reputation": a.reputation,
                    "contributions": a.total_contributions,
                }
                for a in self.agents.values()
            ],
        }


# ════════════════════════════════════════════════════════════════
# FastAPI 엔드포인트
# ════════════════════════════════════════════════════════════════

try:
    from fastapi import FastAPI, UploadFile, File, Form, HTTPException
    from fastapi.responses import FileResponse, JSONResponse

    app = FastAPI(title="화랑 HFL 마스터", version="1.0.0")
    master = HFLMaster()

    @app.get("/hfl/status")
    async def status():
        """시스템 상태 조회."""
        return master.get_status()

    @app.post("/hfl/register")
    async def register(
        agent_id: str = Form(...),
        gpu_name: str = Form(...),
        vram_gb: float = Form(...),
        tier: str = Form(...),
    ):
        """에이전트 등록."""
        return master.register_agent(agent_id, gpu_name, vram_gb, tier)

    @app.post("/hfl/heartbeat")
    async def heartbeat(
        agent_id: str = Form(...),
        metrics: str = Form("{}"),
    ):
        """하트비트 수신."""
        return master.heartbeat(agent_id, json.loads(metrics))

    @app.post("/hfl/round/start")
    async def start_round(config: dict = None):
        """학습 라운드 시작 (관리자용)."""
        return master.start_round(config)

    @app.get("/hfl/round/task/{agent_id}")
    async def get_task(agent_id: str):
        """에이전트 학습 작업 조회."""
        task = master.get_round_task(agent_id)
        if not task:
            return {"task": None}
        return task

    @app.post("/hfl/submit/{round_id}")
    async def submit_lora(
        round_id: str,
        agent_id: str = Form(...),
        metadata: str = Form("{}"),
        lora_file: UploadFile = File(...),
    ):
        """학습된 LoRA 업로드."""
        lora_data = await lora_file.read()
        meta = json.loads(metadata)
        return master.submit_lora(agent_id, round_id, lora_data, meta)

    @app.get("/hfl/lora/latest")
    async def download_latest_lora():
        """최신 통합 LoRA 다운로드."""
        if not master.current_lora_path:
            raise HTTPException(404, "아직 통합된 LoRA가 없습니다")

        lora_file = Path(master.current_lora_path) / "adapter_model.safetensors"
        if not lora_file.exists():
            raise HTTPException(404, "LoRA 파일 없음")

        return FileResponse(
            str(lora_file),
            filename="adapter_model.safetensors",
            headers={"X-LoRA-Version": str(master.current_lora_version)},
        )

    @app.get("/hfl/lora/version")
    async def lora_version():
        """현재 LoRA 버전 조회."""
        return {
            "version": master.current_lora_version,
            "benchmark": master.current_benchmark,
        }

except ImportError:
    logger.warning("FastAPI 없음 → API 엔드포인트 비활성")
    app = None


# ════════════════════════════════════════════════════════════════
# 메인
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="HFL 마스터 서버")
    parser.add_argument("--port", type=int, default=9090)
    parser.add_argument("--storage", default="/mnt/nvme2/hwarang/hfl")
    args = parser.parse_args()

    if app:
        import uvicorn
        master.storage_dir = Path(args.storage)
        uvicorn.run(app, host="0.0.0.0", port=args.port)
    else:
        print("FastAPI 설치 필요: pip install fastapi uvicorn python-multipart")
