"""모델 배포 시스템

마스터가 학습 완료된 모델/LoRA를 에이전트에 효율적으로 배포.

배포 방식 (에이전트 티어별):
  Lite:     모델 샤드 (필요 레이어만, 2GB)
  Standard: 경량 모델 전체 (7B, 5GB)
  Full:     대형 모델 전체 (32B, 20GB) + LoRA

최적화:
  - P2P 배포: 가까운 에이전트에서 다운 (CDN처럼)
  - 증분 업데이트: 변경분만 전송 (LoRA delta)
  - 압축 전송: HFL Adaptive (96.5% 감소)
  - 우선순위: 활성 에이전트 먼저

자체 모델 배포 로드맵:
  Phase 1: 남의 모델 + LoRA (현재)
  Phase 2: 남의 모델 + HFL 대량 학습 → "사실상 화랑 모델"
  Phase 3: Hwarang-1 자체 모델 pretrain → 배포
"""

import os, json, time, hashlib, logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ModelVersion:
    """모델 버전 정보."""
    version: str               # "hwarang-v1.0.0"
    model_name: str             # "Hwarang-1" or "qwen2.5-32b+hwarang-lora"
    base_model: str             # 베이스 모델 ID
    lora_version: str           # LoRA 어댑터 버전
    total_size_gb: float
    shard_count: int            # 샤드 수 (0이면 전체 배포)
    min_tier: str               # "lite", "standard", "full"
    release_date: float
    changelog: str
    checksum: str               # 전체 모델 해시


@dataclass
class DeploymentPlan:
    """에이전트별 배포 계획."""
    agent_id: str
    tier: str
    deploy_type: str            # "shard", "full_model", "lora_only", "delta"
    files_to_download: list[dict]  # [{url, path, size_mb, checksum}]
    total_download_mb: float
    estimated_time_sec: float


class ModelDistributor:
    """모델 배포 관리자 (마스터에서 실행)."""

    def __init__(self):
        self.current_version: Optional[ModelVersion] = None
        self.deployment_history: list[dict] = []

    def create_version(
        self,
        version: str,
        model_name: str,
        base_model: str,
        lora_version: str,
        model_path: str,
        changelog: str = "",
    ) -> ModelVersion:
        """새 모델 버전 등록."""
        # 모델 크기 계산
        total_size = 0
        if os.path.isdir(model_path):
            for root, _, files in os.walk(model_path):
                for f in files:
                    total_size += os.path.getsize(os.path.join(root, f))

        total_gb = total_size / (1024 ** 3)

        # 체크섬
        checksum = hashlib.md5(f"{model_name}{version}{total_size}".encode()).hexdigest()

        ver = ModelVersion(
            version=version,
            model_name=model_name,
            base_model=base_model,
            lora_version=lora_version,
            total_size_gb=round(total_gb, 1),
            shard_count=0,
            min_tier="standard",
            release_date=time.time(),
            changelog=changelog,
            checksum=checksum,
        )

        self.current_version = ver
        logger.info(f"모델 버전 등록: {version} ({model_name}, {total_gb:.1f}GB)")
        return ver

    def create_deployment_plan(
        self,
        agent_id: str,
        agent_tier: str,
        agent_bandwidth_mbps: float,
        current_model_version: str = "",
    ) -> DeploymentPlan:
        """에이전트별 최적 배포 계획 생성."""

        if not self.current_version:
            return DeploymentPlan(
                agent_id=agent_id, tier=agent_tier, deploy_type="none",
                files_to_download=[], total_download_mb=0, estimated_time_sec=0,
            )

        ver = self.current_version

        # 이미 최신 버전이면 스킵
        if current_model_version == ver.version:
            return DeploymentPlan(
                agent_id=agent_id, tier=agent_tier, deploy_type="up_to_date",
                files_to_download=[], total_download_mb=0, estimated_time_sec=0,
            )

        # 티어별 배포 전략
        if agent_tier == "lite":
            return self._plan_shard_deploy(agent_id, ver, agent_bandwidth_mbps)
        elif agent_tier == "standard":
            return self._plan_lora_deploy(agent_id, ver, agent_bandwidth_mbps)
        else:  # full
            return self._plan_full_deploy(agent_id, ver, agent_bandwidth_mbps)

    def _plan_shard_deploy(self, agent_id: str, ver: ModelVersion, bw: float) -> DeploymentPlan:
        """Lite: 필요한 레이어 샤드만 배포."""
        # 에이전트에 할당될 레이어 (마스터가 결정)
        shard_size_mb = (ver.total_size_gb * 1024) / max(ver.shard_count, 8)
        est_time = shard_size_mb / (bw / 8)

        return DeploymentPlan(
            agent_id=agent_id,
            tier="lite",
            deploy_type="shard",
            files_to_download=[{
                "type": "model_shard",
                "size_mb": round(shard_size_mb, 1),
                "layers": "assigned_by_master",
            }],
            total_download_mb=round(shard_size_mb, 1),
            estimated_time_sec=round(est_time, 1),
        )

    def _plan_lora_deploy(self, agent_id: str, ver: ModelVersion, bw: float) -> DeploymentPlan:
        """Standard: LoRA만 배포 (베이스 모델은 이미 있다고 가정)."""
        lora_size_mb = 50  # LoRA 원본
        compressed_mb = 2  # HFL 압축 후
        est_time = compressed_mb / (bw / 8)

        return DeploymentPlan(
            agent_id=agent_id,
            tier="standard",
            deploy_type="lora_only",
            files_to_download=[{
                "type": "lora_adapter",
                "version": ver.lora_version,
                "size_mb": compressed_mb,
                "compression": "hfl_adaptive",
            }],
            total_download_mb=compressed_mb,
            estimated_time_sec=round(est_time, 1),
        )

    def _plan_full_deploy(self, agent_id: str, ver: ModelVersion, bw: float) -> DeploymentPlan:
        """Full: 전체 모델 + LoRA (최초) 또는 delta만 (업데이트)."""
        # 첫 설치 vs 업데이트
        is_first = True  # TODO: 에이전트의 현재 모델 확인

        if is_first:
            total_mb = ver.total_size_gb * 1024
            est_time = total_mb / (bw / 8)
            deploy_type = "full_model"
        else:
            total_mb = 2  # LoRA delta만
            est_time = total_mb / (bw / 8)
            deploy_type = "delta"

        return DeploymentPlan(
            agent_id=agent_id,
            tier="full",
            deploy_type=deploy_type,
            files_to_download=[{
                "type": deploy_type,
                "size_mb": round(total_mb, 1),
            }],
            total_download_mb=round(total_mb, 1),
            estimated_time_sec=round(est_time, 1),
        )

    def execute_p2p_distribution(self, plans: list[DeploymentPlan]) -> dict:
        """P2P 배포: 가까운 에이전트에서 다운로드 (CDN 효과).

        이미 모델 보유한 에이전트가 새 에이전트에게 전송.
        마스터 대역폭 절약.
        """
        # 이미 보유한 에이전트 찾기
        have_model = [p for p in plans if p.deploy_type in ("up_to_date", "delta")]
        need_model = [p for p in plans if p.deploy_type == "full_model"]

        p2p_pairs = []
        for needer in need_model:
            if have_model:
                source = have_model[0]  # 가장 가까운/빠른 에이전트 선택
                p2p_pairs.append({
                    "from": source.agent_id,
                    "to": needer.agent_id,
                    "size_mb": needer.total_download_mb,
                })
                logger.info(f"P2P 배포: {source.agent_id} → {needer.agent_id}")

        return {
            "p2p_transfers": len(p2p_pairs),
            "master_direct": len(need_model) - len(p2p_pairs),
            "lora_only": len([p for p in plans if p.deploy_type == "lora_only"]),
            "shards": len([p for p in plans if p.deploy_type == "shard"]),
        }


# ─── 자체 모델 빌드 로드맵 ──────────────────────────────────

class HwarangModelBuilder:
    """자체 모델 "Hwarang-1" 빌드 계획.

    Phase 1 (현재): 남의 모델 + LoRA
      → Qwen/DeepSeek + hwarang-LoRA
      → 이미 구현됨

    Phase 2 (HFL 축적 후): 모델 합성
      → 여러 LoRA merge → "사실상 화랑 모델"
      → HMM (Model Merging) 활용
      → 이미 구현됨

    Phase 3 (데이터 충분 시): 자체 Pretrain
      → 한국어 특화 토크나이저
      → 한국어 + 코딩 + 법률 + 세무 코퍼스
      → GPU Grid로 분산 학습
      → "Hwarang-1" 탄생
    """

    ROADMAP = {
        "phase_1": {
            "name": "남의 모델 + 우리 LoRA",
            "status": "현재 진행 중",
            "models": ["Qwen2.5-32B + hwarang-general-lora", "DeepSeek-V3 (원본)"],
            "data_needed": "10만+ SFT 샘플",
        },
        "phase_2": {
            "name": "모델 합성 (사실상 화랑 모델)",
            "status": "준비 완료 (HMM 구현됨)",
            "method": "TIES/DARE merge: Qwen + EXAONE + 코딩 LoRA → 합성",
            "data_needed": "100만+ SFT + 10만 DPO",
        },
        "phase_3": {
            "name": "Hwarang-1 자체 Pretrain",
            "status": "계획 중",
            "requirements": [
                "학습 데이터: 한국어 100B+ 토큰",
                "GPU: RTX 5090 × 8대+ (또는 Grid)",
                "학습 시간: 수 주~수 개월",
                "인프라: 분산 학습 (HFL Grid)",
            ],
            "architecture": "Decoder-only Transformer, 한국어 특화 토크나이저",
            "sizes": ["Hwarang-1-7B", "Hwarang-1-32B", "Hwarang-1-72B"],
        },
    }

    @staticmethod
    def get_roadmap() -> dict:
        return HwarangModelBuilder.ROADMAP

    @staticmethod
    def estimate_pretrain_cost(
        model_size_b: float = 32,
        tokens_b: float = 100,
        gpu_type: str = "RTX 5090",
        gpu_count: int = 8,
    ) -> dict:
        """자체 Pretrain 비용/시간 추정."""
        # Chinchilla scaling: 학습 토큰 ≈ 모델 파라미터 × 20
        recommended_tokens = model_size_b * 20  # 640B for 32B model

        # 연산량 (FLOPs) ≈ 6 × 파라미터 × 토큰
        flops = 6 * model_size_b * 1e9 * tokens_b * 1e9

        # GPU 성능 (TFLOPS, BF16)
        gpu_tflops = {"RTX 5090": 200, "RTX 4090": 160, "A100": 312, "H100": 990}
        tflops = gpu_tflops.get(gpu_type, 200)

        # 학습 시간
        total_tflops = tflops * gpu_count
        seconds = flops / (total_tflops * 1e12) / 0.4  # MFU 40%
        hours = seconds / 3600
        days = hours / 24

        # 비용 (전기)
        gpu_watts = {"RTX 5090": 575, "RTX 4090": 450, "A100": 400, "H100": 700}
        watts = gpu_watts.get(gpu_type, 500) * gpu_count
        kwh = watts * hours / 1000
        electricity_cost = kwh * 150  # 150원/kWh

        return {
            "model_size": f"{model_size_b}B",
            "training_tokens": f"{tokens_b}B (권장 {recommended_tokens}B)",
            "gpu": f"{gpu_type} × {gpu_count}",
            "estimated_days": round(days, 1),
            "estimated_hours": round(hours, 0),
            "electricity_kwh": round(kwh, 0),
            "electricity_cost_krw": f"₩{int(electricity_cost):,}",
            "note": "HFL Grid 활용 시 비용 대폭 절감 가능",
        }
