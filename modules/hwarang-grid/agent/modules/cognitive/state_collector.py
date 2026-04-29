"""에이전트 자기 상태 수집.

신호:
- GPU: VRAM 사용률, 활성 작업
- 시스템: CPU, 메모리, 배터리 (노트북)
- 시간: 사용자 활동 시간 / 야간
- 학습 이력: 최근 라운드 품질 점수 / 보상
- 도메인 전문성: 가진 LoRA / 자격증

모든 _xxx() 헬퍼는 부분적 환경(예: pynvml/psutil 미설치)에서도
예외를 삼키고 안전한 기본값을 돌려주도록 구현.
"""

import asyncio
import json
import logging
import os
import platform
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    # GPU
    gpu_vram_used_gb: float
    gpu_vram_total_gb: float
    gpu_utilization_pct: float
    gpu_idle: bool

    # 시스템
    cpu_idle_pct: float
    ram_free_gb: float
    is_on_battery: bool
    battery_pct: Optional[float]

    # 시간 (사용자 환경)
    is_user_active: bool   # 마우스/키보드 사용 중?
    is_peak_hours: bool    # 사용자 활동 시간대 (09~22 KST)
    is_night: bool         # 야간 (23~06)

    # 학습 이력
    last_round_score: Optional[float]   # 0~1 (마지막 라운드 품질)
    rounds_completed_today: int
    rounds_failed_today: int

    # 전문성
    available_loras: list[str]
    expert_credentials: list[str]   # ["BAR_KR:123", "MD_KR:456"]

    # 보상
    total_hwr_today: float


async def collect_state() -> AgentState:
    """현재 에이전트 상태 수집.

    동기 호출이지만 async 컨텍스트에서 부르기 쉽도록 코루틴으로 노출.
    psutil cpu_percent 가 약 0.5초 블록 → 필요 시 to_thread 가능.
    """
    return AgentState(
        gpu_vram_used_gb=_gpu_vram_used(),
        gpu_vram_total_gb=_gpu_vram_total(),
        gpu_utilization_pct=_gpu_util(),
        gpu_idle=_gpu_util() < 20,
        cpu_idle_pct=_cpu_idle(),
        ram_free_gb=_ram_free_gb(),
        is_on_battery=_is_on_battery(),
        battery_pct=_battery_pct(),
        is_user_active=_user_active(),
        is_peak_hours=_is_peak_hours(),
        is_night=_is_night(),
        last_round_score=_last_round_score(),
        rounds_completed_today=_rounds_today("completed"),
        rounds_failed_today=_rounds_today("failed"),
        available_loras=_available_loras(),
        expert_credentials=_expert_credentials(),
        total_hwr_today=_total_hwr_today(),
    )


# ─── GPU ──────────────────────────────────────────────


def _gpu_vram_used() -> float:
    try:
        import pynvml
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(h)
        return info.used / 1024 / 1024 / 1024
    except Exception:
        return 0.0


def _gpu_vram_total() -> float:
    try:
        import pynvml
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(h)
        return info.total / 1024 / 1024 / 1024
    except Exception:
        return 0.0


def _gpu_util() -> float:
    try:
        import pynvml
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        u = pynvml.nvmlDeviceGetUtilizationRates(h)
        return float(u.gpu)
    except Exception:
        return 0.0


# ─── 시스템 ────────────────────────────────────────────


def _cpu_idle() -> float:
    try:
        import psutil
        return 100.0 - psutil.cpu_percent(interval=0.5)
    except Exception:
        return 50.0


def _ram_free_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().available / 1024 ** 3
    except Exception:
        return 4.0


def _is_on_battery() -> bool:
    try:
        import psutil
        b = psutil.sensors_battery()
        return b is not None and not b.power_plugged
    except Exception:
        return False


def _battery_pct() -> Optional[float]:
    try:
        import psutil
        b = psutil.sensors_battery()
        return b.percent if b else None
    except Exception:
        return None


# ─── 시간/사용자 ────────────────────────────────────────


def _user_active() -> bool:
    """마우스/키보드 활동 감지 — OS 별 진짜 idle.

    user_activity 모듈에 위임 (macOS: ioreg, Linux: xprintidle, Windows: GetLastInputInfo).
    감지 실패 시에는 피크시간대 추정으로 폴백 (이전 stub 동작).
    """
    try:
        from .user_activity import is_user_active
        return is_user_active(threshold_seconds=60)
    except Exception as exc:
        logger.debug("user_activity 모듈 사용 실패, 시간대 폴백: %s", exc)
        return _is_peak_hours()


def _is_peak_hours() -> bool:
    """KST 09~22 = 사용자 활동 시간대."""
    from datetime import datetime
    try:
        import zoneinfo
        now = datetime.now(zoneinfo.ZoneInfo("Asia/Seoul"))
    except Exception:
        now = datetime.now()
    return 9 <= now.hour < 22


def _is_night() -> bool:
    """KST 23~06 = 야간 (전기료 낮음 + 사용자 활동 낮음)."""
    from datetime import datetime
    try:
        import zoneinfo
        now = datetime.now(zoneinfo.ZoneInfo("Asia/Seoul"))
    except Exception:
        now = datetime.now()
    return now.hour >= 23 or now.hour < 6


# ─── 학습 이력 ──────────────────────────────────────────


def _last_round_score() -> Optional[float]:
    """earnings_tracker 의 최근 라운드 점수 — 캐시 파일에서 읽기."""
    cache_path = Path.home() / ".hwarang" / "agent_recent.json"
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text())
        v = data.get("last_round_score")
        return float(v) if v is not None else None
    except Exception:
        return None


def _rounds_today(status: str) -> int:
    """오늘 완료/실패 라운드 수 (캐시).

    status: "completed" | "failed"
    """
    cache_path = Path.home() / ".hwarang" / "agent_stats.json"
    if not cache_path.exists():
        return 0
    try:
        data = json.loads(cache_path.read_text())
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        return int(data.get(today, {}).get(f"rounds_{status}", 0))
    except Exception:
        return 0


# ─── 전문성 ────────────────────────────────────────────


def _available_loras() -> list[str]:
    """현재 보유 LoRA 어댑터 — config 에서 읽기."""
    try:
        from hwarang_agent.config.agent_config import AgentConfig  # type: ignore
        cfg = AgentConfig.load()
        return list(getattr(cfg, "available_loras", []) or [])
    except Exception:
        # 패키지 경로 다른 경우 폴백
        try:
            from config.agent_config import AgentConfig  # type: ignore
            cfg = AgentConfig.load()
            return list(getattr(cfg, "available_loras", []) or [])
        except Exception:
            return []


def _expert_credentials() -> list[str]:
    """소유자 자격증 — link-account 에서 등록한 것."""
    cache_path = Path.home() / ".hwarang" / "account.json"
    if not cache_path.exists():
        return []
    try:
        data = json.loads(cache_path.read_text())
        creds = data.get("expert_credentials", [])
        if isinstance(creds, str):
            creds = [creds]
        return [str(c) for c in creds]
    except Exception:
        return []


def _total_hwr_today() -> float:
    """오늘 누적 HWR 보상."""
    cache_path = Path.home() / ".hwarang" / "earnings.json"
    if not cache_path.exists():
        return 0.0
    try:
        data = json.loads(cache_path.read_text())
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        return float(data.get(today, 0))
    except Exception:
        return 0.0
