"""에이전트 설정 시스템

각 에이전트(Grid PC)가 어떤 역할을 수행할지 설정.
설정은 로컬 JSON 파일 + 마스터 원격 설정으로 관리.

설정 항목:
  - 어떤 모듈 활성화? (서빙/학습/크롤링/검증 등)
  - GPU 자원 할당 (서빙 50%, 학습 30%, 유휴 20%)
  - 네트워크 제한 (업로드 상한, 대역폭 %)
  - 보상 설정 (최소 보상 임계값)
  - 운영 시간 (24시간 or 야간만 등)
  - 자동 업데이트 여부

사용법:
    from config.agent_config import AgentConfig
    config = AgentConfig.load()
    if config.modules.serving.enabled:
        start_serving()
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path


CONFIG_PATH = os.path.expanduser("~/.hwarang/agent_config.json")


# ─── 모듈별 설정 ────────────────────────────────────────────

@dataclass
class ServingConfig:
    """추론 서빙 설정."""
    enabled: bool = True
    max_concurrent: int = 4          # 최대 동시 요청
    gpu_memory_percent: float = 0.5  # GPU 메모리 할당 비율
    models: list[str] = field(default_factory=lambda: ["hwarang-general"])
    priority: int = 1                # 우선순위 (1=최우선)

@dataclass
class LearningConfig:
    """HFL 학습 설정."""
    enabled: bool = True
    max_gpu_percent: float = 0.3     # 학습에 할당할 GPU %
    steps_per_round: int = 500
    auto_accept_tasks: bool = True   # 학습 과제 자동 수락
    preferred_domains: list[str] = field(default_factory=lambda: ["coding", "legal", "tax"])
    priority: int = 2

@dataclass
class CrawlingConfig:
    """데이터 크롤링 설정."""
    enabled: bool = False
    sources: list[str] = field(default_factory=lambda: ["news", "law", "code"])
    interval_hours: int = 24         # 크롤링 주기
    max_items_per_run: int = 100
    storage_limit_mb: int = 500      # 로컬 저장 상한
    priority: int = 5

@dataclass
class BenchmarkConfig:
    """벤치마크/테스트 설정."""
    enabled: bool = True
    auto_benchmark_new_lora: bool = True  # 새 LoRA 자동 벤치마크
    benchmark_samples: int = 50
    report_to_master: bool = True
    priority: int = 3

@dataclass
class RAGConfig:
    """RAG 인덱싱 설정."""
    enabled: bool = False
    index_local_docs: bool = False   # 로컬 문서 인덱싱
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    max_docs: int = 1000
    priority: int = 6

@dataclass
class MonitoringConfig:
    """시스템 모니터링 설정."""
    enabled: bool = True
    report_interval_sec: int = 60    # 리포트 주기
    alert_gpu_temp: int = 85         # GPU 온도 경고 (°C)
    alert_gpu_util: float = 0.95     # GPU 사용률 경고
    alert_vram_percent: float = 0.95 # VRAM 사용률 경고
    priority: int = 7

@dataclass
class ABTestConfig:
    """A/B 테스트 설정."""
    enabled: bool = True
    auto_run: bool = True
    samples_per_test: int = 100      # 테스트당 샘플 수
    report_to_master: bool = True
    priority: int = 4

@dataclass
class CacheConfig:
    """응답 캐시 설정."""
    enabled: bool = True
    max_cache_mb: int = 200          # 캐시 크기 상한
    ttl_hours: int = 24              # 캐시 만료 시간
    min_frequency: int = 3           # 최소 N번 질문되면 캐시
    priority: int = 8

@dataclass
class SafetyConfig:
    """안전 필터 설정."""
    enabled: bool = True
    filter_harmful: bool = True      # 유해 콘텐츠 필터
    filter_hallucination: bool = True  # 환각 감지
    filter_pii: bool = True          # 개인정보 감지
    log_violations: bool = True
    priority: int = 2

@dataclass
class RewardVerificationConfig:
    """보상 검증 설정 (코인 부정 수급 방지)."""
    enabled: bool = True
    verify_gpu_benchmark: bool = True  # 실제 GPU 능력 검증
    verify_work_proof: bool = True     # 작업 증명 검증
    report_suspicious: bool = True     # 의심 활동 신고
    priority: int = 1

@dataclass
class AutoUpdateConfig:
    """자동 업데이트 설정."""
    enabled: bool = True
    check_interval_hours: int = 6
    auto_restart: bool = False       # 업데이트 후 자동 재시작
    channel: str = "stable"          # stable, beta, dev


# ─── 전체 설정 ───────────────────────────────────────────────

@dataclass
class NetworkConfig:
    """네트워크 설정."""
    master_url: str = "https://grid.hwarang.ai"
    upload_limit_mbps: float = 0      # 0 = 무제한
    download_limit_mbps: float = 0
    use_bandwidth_percent: float = 0.8  # 전체 대역폭의 80%만 사용

@dataclass
class ScheduleConfig:
    """운영 시간 설정."""
    mode: str = "always"              # always, scheduled, idle_only
    start_hour: int = 0               # scheduled 모드: 시작 시간
    end_hour: int = 24                # scheduled 모드: 종료 시간
    idle_threshold_min: int = 5       # idle_only: N분 유휴 후 시작
    pause_on_user_activity: bool = True  # 유저 작업 감지 시 일시 중지

@dataclass
class RewardConfig:
    """보상 설정."""
    wallet_address: str = ""          # 코인 수령 지갑 주소
    min_payout_hwr: float = 10        # 최소 출금 단위
    auto_compound: bool = False       # 보상 자동 재투자
    prefer_learning_reward: bool = True  # 학습 보상 (2x) 선호

@dataclass
class ModulesConfig:
    """전체 모듈 설정."""
    serving: ServingConfig = field(default_factory=ServingConfig)
    learning: LearningConfig = field(default_factory=LearningConfig)
    crawling: CrawlingConfig = field(default_factory=CrawlingConfig)
    benchmark: BenchmarkConfig = field(default_factory=BenchmarkConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    ab_test: ABTestConfig = field(default_factory=ABTestConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    reward_verification: RewardVerificationConfig = field(default_factory=RewardVerificationConfig)
    auto_update: AutoUpdateConfig = field(default_factory=AutoUpdateConfig)


@dataclass
class AgentConfig:
    """에이전트 전체 설정."""

    # 기본 정보
    agent_id: str = ""
    agent_name: str = "화랑 에이전트"
    region: str = "kr"

    # 하위 설정
    network: NetworkConfig = field(default_factory=NetworkConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    reward: RewardConfig = field(default_factory=RewardConfig)
    modules: ModulesConfig = field(default_factory=ModulesConfig)

    # ─── 저장 / 로드 ────────────────────────────────

    def save(self, path: str = CONFIG_PATH):
        """설정 저장."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str = CONFIG_PATH) -> "AgentConfig":
        """설정 로드. 없으면 기본값."""
        if not os.path.exists(path):
            config = cls()
            config.save(path)
            return config

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict) -> "AgentConfig":
        """딕셔너리에서 설정 생성."""
        config = cls()
        for key, value in data.items():
            if hasattr(config, key):
                attr = getattr(config, key)
                if hasattr(attr, '__dataclass_fields__'):
                    # 중첩 dataclass
                    for sub_key, sub_val in value.items():
                        sub_attr = getattr(attr, sub_key, None)
                        if sub_attr is not None and hasattr(sub_attr, '__dataclass_fields__'):
                            for k, v in sub_val.items():
                                if hasattr(sub_attr, k):
                                    setattr(sub_attr, k, v)
                        elif hasattr(attr, sub_key):
                            setattr(attr, sub_key, sub_val)
                else:
                    setattr(config, key, value)
        return config

    # ─── 활성 모듈 목록 ─────────────────────────────

    def get_enabled_modules(self) -> list[str]:
        """활성화된 모듈 이름 목록."""
        modules = []
        for name in self.modules.__dataclass_fields__:
            mod = getattr(self.modules, name)
            if hasattr(mod, 'enabled') and mod.enabled:
                modules.append(name)
        return sorted(modules, key=lambda n: getattr(getattr(self.modules, n), 'priority', 99))

    def print_config(self):
        """현재 설정 출력."""
        print("\n" + "=" * 60)
        print(f" 화랑 에이전트 설정: {self.agent_name}")
        print("=" * 60)
        print(f"  ID:       {self.agent_id}")
        print(f"  지역:     {self.region}")
        print(f"  마스터:   {self.network.master_url}")
        print(f"  운영 모드: {self.schedule.mode}")
        print(f"  지갑:     {self.reward.wallet_address or '(미설정)'}")

        enabled = self.get_enabled_modules()
        disabled = [n for n in self.modules.__dataclass_fields__ if n not in enabled]

        print(f"\n  활성 모듈 ({len(enabled)}):")
        for name in enabled:
            mod = getattr(self.modules, name)
            priority = getattr(mod, 'priority', '-')
            print(f"    ✅ {name:<25} (우선순위 {priority})")

        print(f"\n  비활성 모듈 ({len(disabled)}):")
        for name in disabled:
            print(f"    ❌ {name}")

        print("=" * 60)


# ─── 프리셋 ──────────────────────────────────────────────────

def preset_minimal() -> AgentConfig:
    """최소 설정 (서빙만)."""
    config = AgentConfig(agent_name="최소 에이전트")
    config.modules.learning.enabled = False
    config.modules.crawling.enabled = False
    config.modules.rag.enabled = False
    config.modules.ab_test.enabled = False
    config.modules.cache.enabled = False
    return config

def preset_full() -> AgentConfig:
    """전체 활성화."""
    config = AgentConfig(agent_name="풀 에이전트")
    config.modules.crawling.enabled = True
    config.modules.rag.enabled = True
    return config

def preset_learning_focused() -> AgentConfig:
    """학습 중심."""
    config = AgentConfig(agent_name="학습 에이전트")
    config.modules.learning.max_gpu_percent = 0.7
    config.modules.serving.gpu_memory_percent = 0.2
    config.modules.crawling.enabled = True
    return config

def preset_night_only() -> AgentConfig:
    """야간 전용."""
    config = AgentConfig(agent_name="야간 에이전트")
    config.schedule.mode = "scheduled"
    config.schedule.start_hour = 23
    config.schedule.end_hour = 7
    config.modules.learning.max_gpu_percent = 0.8
    return config


# ─── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="화랑 에이전트 설정")
    parser.add_argument("action", choices=["show", "init", "preset", "enable", "disable", "set"])
    parser.add_argument("--preset", choices=["minimal", "full", "learning", "night"])
    parser.add_argument("--module", help="모듈 이름")
    parser.add_argument("--key", help="설정 키")
    parser.add_argument("--value", help="설정 값")
    args = parser.parse_args()

    if args.action == "show":
        config = AgentConfig.load()
        config.print_config()

    elif args.action == "init":
        config = AgentConfig()
        config.save()
        print(f"기본 설정 생성: {CONFIG_PATH}")
        config.print_config()

    elif args.action == "preset":
        presets = {
            "minimal": preset_minimal,
            "full": preset_full,
            "learning": preset_learning_focused,
            "night": preset_night_only,
        }
        if args.preset in presets:
            config = presets[args.preset]()
            config.save()
            print(f"프리셋 '{args.preset}' 적용")
            config.print_config()

    elif args.action == "enable" and args.module:
        config = AgentConfig.load()
        mod = getattr(config.modules, args.module, None)
        if mod and hasattr(mod, 'enabled'):
            mod.enabled = True
            config.save()
            print(f"✅ {args.module} 활성화")

    elif args.action == "disable" and args.module:
        config = AgentConfig.load()
        mod = getattr(config.modules, args.module, None)
        if mod and hasattr(mod, 'enabled'):
            mod.enabled = False
            config.save()
            print(f"❌ {args.module} 비활성화")
