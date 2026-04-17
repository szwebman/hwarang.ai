"""에이전트 3단계 모드 (Lite / Standard / Full)

에이전트 참여 진입장벽을 최소화.
Lite = 설치 0GB, 누구나 클릭 한 번으로 참여.

┌──────────────────────────────────────────────────┐
│  Lite (0GB)       Standard (5~10GB)    Full (20~50GB)  │
│  GPU만 빌려줌     경량 모델 서빙       대형 모델 학습   │
│  모델 없음        7B 로컬             32B 로컬         │
│  마스터 의존      부분 독립           완전 독립        │
│  보상 ×1.0        보상 ×1.5           보상 ×3.0       │
│  진입: 클릭 1번   진입: 10분 설치     진입: 1시간 설치  │
└──────────────────────────────────────────────────┘
"""

from dataclasses import dataclass, field
from enum import Enum


class AgentTier(Enum):
    LITE = "lite"           # 0GB, GPU만 빌려줌
    STANDARD = "standard"   # 5~10GB, 경량 모델
    FULL = "full"           # 20~50GB, 대형 모델


@dataclass
class TierConfig:
    tier: AgentTier
    display_name: str
    description: str

    # 설치 요구
    min_vram_gb: float
    min_disk_gb: float
    min_ram_gb: float

    # 로컬 모델
    local_model: str           # 로컬에 설치할 모델
    local_model_size_gb: float

    # 활성 모듈
    enabled_modules: list[str]

    # 보상
    reward_multiplier: float

    # 네트워크
    needs_internet: str        # always, mostly, sometimes


# ─── 3단계 프리셋 ────────────────────────────────────────────

TIER_CONFIGS = {
    AgentTier.LITE: TierConfig(
        tier=AgentTier.LITE,
        display_name="Lite (초경량)",
        description="설치 0GB. GPU만 빌려주면 됩니다. 클릭 한 번으로 시작.",
        min_vram_gb=4,
        min_disk_gb=0.1,       # 에이전트 앱만 (50MB)
        min_ram_gb=4,
        local_model="none",    # 로컬 모델 없음
        local_model_size_gb=0,
        enabled_modules=[
            "monitoring",       # 시스템 모니터링
            "reward_verification",  # 보상 검증
            "reputation",       # 평판
            "sleep_learning",   # 수면 학습 (마스터가 작업 전송)
            "offline_agent",    # 오프라인 감지
            "auto_update",      # 자동 업데이트
        ],
        reward_multiplier=1.0,
        needs_internet="always",
    ),

    AgentTier.STANDARD: TierConfig(
        tier=AgentTier.STANDARD,
        display_name="Standard (표준)",
        description="경량 모델(7B) 설치. 서빙 + 캐시 + 기본 학습 가능.",
        min_vram_gb=8,
        min_disk_gb=10,
        min_ram_gb=8,
        local_model="qwen2.5-7b",
        local_model_size_gb=5,
        enabled_modules=[
            "serving",          # AI 서빙
            "monitoring",
            "reward_verification",
            "reputation",
            "sleep_learning",
            "cache",            # 응답 캐시
            "safety",           # 안전 필터
            "benchmark",        # 벤치마크
            "offline_agent",
            "auto_update",
            "auto_specialization",
            "ai_mentor",
        ],
        reward_multiplier=1.5,
        needs_internet="mostly",
    ),

    AgentTier.FULL: TierConfig(
        tier=AgentTier.FULL,
        display_name="Full (전체)",
        description="대형 모델(32B) 설치. 학습 + 서빙 + 길드 + 모든 기능.",
        min_vram_gb=16,
        min_disk_gb=50,
        min_ram_gb=16,
        local_model="qwen2.5-32b-int4",
        local_model_size_gb=20,
        enabled_modules=[
            "serving", "learning", "crawling", "benchmark",
            "rag", "monitoring", "ab_test", "cache", "safety",
            "reward_verification", "auto_update", "translator",
            "sleep_learning", "ai_mentor", "p2p_collaboration",
            "marketplace", "agent_dna", "local_finetune",
            "reputation", "auto_specialization", "offline_agent",
            "agent_guild",
        ],
        reward_multiplier=3.0,
        needs_internet="sometimes",
    ),
}


# ─── 자동 티어 감지 ──────────────────────────────────────────

def detect_best_tier() -> AgentTier:
    """현재 PC 스펙으로 최적 티어 자동 감지."""
    vram = _get_gpu_vram()
    disk_free = _get_disk_free()
    ram = _get_ram()

    if vram >= 16 and disk_free >= 50 and ram >= 16:
        return AgentTier.FULL
    elif vram >= 8 and disk_free >= 10 and ram >= 8:
        return AgentTier.STANDARD
    else:
        return AgentTier.LITE


def _get_gpu_vram() -> float:
    """GPU VRAM (GB)."""
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        return float(result.stdout.strip()) / 1024
    except:
        return 0


def _get_disk_free() -> float:
    """디스크 여유 공간 (GB)."""
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        return free / (1024 ** 3)
    except:
        return 0


def _get_ram() -> float:
    """시스템 RAM (GB)."""
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except:
        try:
            import os
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024 ** 3)
        except:
            return 0


# ─── 모델 샤딩 (Lite 모드용) ─────────────────────────────────

@dataclass
class ModelShard:
    """모델 조각 (에이전트에 배포되는 단위)."""
    shard_id: str
    model_name: str
    layer_start: int
    layer_end: int
    size_mb: float
    assigned_agent: str = ""


def create_model_shards(
    model_name: str,
    total_layers: int,
    total_size_gb: float,
    num_shards: int,
) -> list[ModelShard]:
    """모델을 N개 조각으로 분할.

    예: 32B 모델 (32 레이어, 18GB) → 8개 샤드 (각 4레이어, 2.25GB)
    """
    layers_per_shard = total_layers // num_shards
    size_per_shard_mb = (total_size_gb * 1024) / num_shards

    shards = []
    for i in range(num_shards):
        start = i * layers_per_shard
        end = start + layers_per_shard
        if i == num_shards - 1:
            end = total_layers  # 마지막 샤드가 나머지 흡수

        shards.append(ModelShard(
            shard_id=f"{model_name}_shard_{i}",
            model_name=model_name,
            layer_start=start,
            layer_end=end,
            size_mb=round(size_per_shard_mb, 1),
        ))

    return shards


# ─── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    # 자동 감지
    tier = detect_best_tier()
    config = TIER_CONFIGS[tier]

    print(f"\n{'='*60}")
    print(f" 화랑 에이전트 티어 감지")
    print(f"{'='*60}")
    print(f"  감지된 티어: {config.display_name}")
    print(f"  설명: {config.description}")
    print(f"  GPU VRAM: {_get_gpu_vram():.1f}GB (필요 {config.min_vram_gb}GB)")
    print(f"  디스크: {_get_disk_free():.1f}GB (필요 {config.min_disk_gb}GB)")
    print(f"  RAM: {_get_ram():.1f}GB (필요 {config.min_ram_gb}GB)")
    print(f"  로컬 모델: {config.local_model} ({config.local_model_size_gb}GB)")
    print(f"  활성 모듈: {len(config.enabled_modules)}개")
    print(f"  보상 배율: ×{config.reward_multiplier}")
    print(f"{'='*60}")

    # 모델 샤딩 예시
    print(f"\n모델 샤딩 예시 (32B, 8대 Lite 에이전트):")
    shards = create_model_shards("qwen2.5-32b", 32, 18, 8)
    for s in shards:
        print(f"  {s.shard_id}: Layer {s.layer_start}~{s.layer_end-1} ({s.size_mb}MB)")
    print(f"  → 각 에이전트 {shards[0].size_mb}MB만 다운로드!")
