"""에이전트 상태 → JSON 파일 작성기.

Tauri Rust 앱이 `~/.hwarang/agent_status.json` 을 읽어 트레이에 표시한다.
Python 데몬이 30초마다 이 파일을 갱신해야 한다.

JSON 스키마 (Rust main.rs 와 일치):

  {
    "status": "running" | "idle" | "stopped" | "error",
    "gpu_name": "NVIDIA RTX 4090",
    "gpu_usage_percent": 75.3,
    "gpu_temp": 68,
    "tokens_today": 1234,
    "tokens_total": 56789,
    "uptime_minutes": 142,
    "work_count_today": 5,
    "connected": true,
    "current_round_id": "law-lora-v3" | null,
    "current_round_progress": 0.42,
    "active_rounds_count": 1,
    "kyc_verified": true,
    "tier": "GOLD",
    "last_error": null,
    "updated_at": "2026-04-23T10:30:00Z"
  }
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

# 선택적 의존성들 — 없어도 graceful degrade
try:
    import httpx  # type: ignore
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

try:
    from . import gpu_detector  # type: ignore
except Exception:  # pragma: no cover
    try:
        from modules import gpu_detector  # type: ignore
    except Exception:
        gpu_detector = None  # type: ignore

try:
    from . import participation_control  # type: ignore
except Exception:  # pragma: no cover
    try:
        from modules import participation_control  # type: ignore
    except Exception:
        participation_control = None  # type: ignore

try:
    from . import earnings_tracker  # type: ignore
except Exception:  # pragma: no cover
    try:
        from modules import earnings_tracker  # type: ignore
    except Exception:
        earnings_tracker = None  # type: ignore


# ────────────────────────────────────────────────────────────────────────
# 경로 / 캐시
# ────────────────────────────────────────────────────────────────────────

HOME_DIR = Path.home() / ".hwarang"
STATUS_FILE = HOME_DIR / "agent_status.json"

# HLKM(프로필 + KYC + tier) API 호출 캐시 — 너무 자주 부르지 않게
_PROFILE_CACHE: dict[str, Any] = {"data": None, "fetched_at": 0.0}
_PROFILE_TTL_SEC = 300  # 5분

# 수익 캐시
_EARNINGS_CACHE: dict[str, Any] = {"data": None, "fetched_at": 0.0}
_EARNINGS_TTL_SEC = 60


def status_path() -> Path:
    """상태 파일 절대 경로 (~/.hwarang/agent_status.json)."""
    return STATUS_FILE


def _ensure_dir() -> None:
    HOME_DIR.mkdir(parents=True, exist_ok=True)


# ────────────────────────────────────────────────────────────────────────
# 기본 상태 + 작성
# ────────────────────────────────────────────────────────────────────────


def default_state() -> dict[str, Any]:
    """모든 키가 채워진 기본 상태 (Rust 측 기본값과 일치).

    Rust 가 읽는 필드 호환:
      - current_round_id     (Option<String>)
      - current_round_name   (String, 빈 문자열 가능)  ← Tauri 알림에서 사용
      - current_round_progress, active_rounds_count, tier 는 status_writer 확장 정보
    """
    return {
        "status": "stopped",
        "gpu_name": "감지 중...",
        "gpu_usage_percent": 0.0,
        "gpu_temp": 0,
        "tokens_today": 0,
        "tokens_total": 0,
        "uptime_minutes": 0,
        "work_count_today": 0,
        "connected": False,
        "current_round_id": None,
        "current_round_name": "",
        "current_round_progress": 0.0,
        "active_rounds_count": 0,
        "kyc_verified": False,
        "tier": "BRONZE",
        "last_error": None,
        "updated_at": _now_iso(),
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def write_status(state: dict[str, Any]) -> None:
    """상태 dict 를 JSON 파일로 atomic 저장."""
    _ensure_dir()
    payload = dict(default_state())
    payload.update(state or {})
    payload["updated_at"] = _now_iso()

    # atomic write — 임시 파일에 쓴 뒤 rename
    tmp = STATUS_FILE.with_suffix(".json.tmp")
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _sync_write, tmp, payload)
        await loop.run_in_executor(None, os.replace, str(tmp), str(STATUS_FILE))
    except Exception as exc:
        logger.warning("상태 파일 작성 실패: %s", exc)


def write_status_sync(state: dict[str, Any]) -> None:
    """동기 버전 (signal handler / shutdown 경로 등에서)."""
    _ensure_dir()
    payload = dict(default_state())
    payload.update(state or {})
    payload["updated_at"] = _now_iso()

    tmp = STATUS_FILE.with_suffix(".json.tmp")
    try:
        _sync_write(tmp, payload)
        os.replace(str(tmp), str(STATUS_FILE))
    except Exception as exc:
        logger.warning("상태 파일 작성 실패: %s", exc)


def _sync_write(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# ────────────────────────────────────────────────────────────────────────
# 외부 데이터 수집 (캐시)
# ────────────────────────────────────────────────────────────────────────


def _gpu_state() -> dict[str, Any]:
    """GPU 정보 + 메트릭."""
    out: dict[str, Any] = {
        "gpu_name": "감지 중...",
        "gpu_usage_percent": 0.0,
        "gpu_temp": 0,
    }
    if gpu_detector is None:
        return out
    try:
        info = gpu_detector.detect_gpu()
        out["gpu_name"] = info.get("name", "Unknown GPU")
    except Exception as exc:
        logger.debug("GPU 감지 실패: %s", exc)

    try:
        metrics = gpu_detector.get_gpu_metrics()
        out["gpu_usage_percent"] = float(metrics.get("usage_percent", 0))
        out["gpu_temp"] = int(metrics.get("temp_c", 0))
    except Exception as exc:
        logger.debug("GPU 메트릭 실패: %s", exc)
    return out


def _round_state() -> dict[str, Any]:
    """활성 라운드 정보."""
    out: dict[str, Any] = {
        "current_round_id": None,
        "current_round_progress": 0.0,
        "active_rounds_count": 0,
    }
    if participation_control is None:
        return out
    try:
        active = participation_control.list_active_rounds()
        out["active_rounds_count"] = len(active)
        if active:
            # 진행률 가장 큰 라운드를 "current" 로 표시
            current = max(active, key=lambda r: float(r.get("progress", 0) or 0))
            out["current_round_id"] = current.get("round_id")
            out["current_round_progress"] = float(current.get("progress", 0) or 0)
            # Rust 알림 코드에서 참조하는 표시명 (없으면 round_id 로 폴백)
            out["current_round_name"] = (
                current.get("round_name") or current.get("round_id") or ""
            )
    except Exception as exc:
        logger.debug("active_rounds 조회 실패: %s", exc)
    return out


async def _earnings_state(
    master_url: str | None,
    agent_id: str | None,
    api_key: str | None,
) -> dict[str, Any]:
    """수익 — tokens_today / tokens_total / work_count_today.

    캐시: _EARNINGS_TTL_SEC 동안 재사용.
    """
    out = {
        "tokens_today": 0,
        "tokens_total": 0,
        "work_count_today": 0,
    }
    if not (master_url and agent_id and api_key):
        return out
    if earnings_tracker is None:
        return out

    now = time.time()
    if (
        _EARNINGS_CACHE["data"] is not None
        and (now - _EARNINGS_CACHE["fetched_at"]) < _EARNINGS_TTL_SEC
    ):
        return dict(_EARNINGS_CACHE["data"])

    try:
        records = await earnings_tracker.fetch_earnings(
            master_url=master_url,
            agent_id=agent_id,
            api_key=api_key,
            since=None,
        )
    except Exception as exc:
        logger.debug("수익 조회 실패: %s", exc)
        return out

    today = datetime.now(timezone.utc).date()
    tokens_today = 0
    tokens_total = 0
    work_today = 0
    for r in records:
        reward = int(getattr(r, "reward", 0) or 0)
        tokens_total += reward
        completed_at = getattr(r, "completed_at", None) or getattr(r, "at", None)
        if hasattr(completed_at, "date"):
            try:
                if completed_at.date() == today:
                    tokens_today += reward
                    work_today += 1
            except Exception:
                pass

    out["tokens_today"] = tokens_today
    out["tokens_total"] = tokens_total
    out["work_count_today"] = work_today

    _EARNINGS_CACHE["data"] = dict(out)
    _EARNINGS_CACHE["fetched_at"] = now
    return out


async def _profile_state(
    master_url: str | None,
    agent_id: str | None,
    api_key: str | None,
) -> dict[str, Any]:
    """HLKM 프로필 (tier + kyc).

    GET /api/grid/agents/{agent_id}/profile (또는 fallback)
    """
    out = {"tier": "BRONZE", "kyc_verified": False}
    if not (master_url and agent_id and api_key):
        return out
    if httpx is None:
        return out

    now = time.time()
    if (
        _PROFILE_CACHE["data"] is not None
        and (now - _PROFILE_CACHE["fetched_at"]) < _PROFILE_TTL_SEC
    ):
        return dict(_PROFILE_CACHE["data"])

    url = f"{master_url.rstrip('/')}/api/grid/agents/{agent_id}/profile"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json() or {}
                out["tier"] = str(data.get("tier", "BRONZE")).upper()
                out["kyc_verified"] = bool(data.get("kyc_verified", False))
                _PROFILE_CACHE["data"] = dict(out)
                _PROFILE_CACHE["fetched_at"] = now
            else:
                logger.debug("profile API HTTP %s", resp.status_code)
    except Exception as exc:
        logger.debug("profile 조회 실패: %s", exc)
    return out


# ────────────────────────────────────────────────────────────────────────
# Agent 인스턴스에서 상태 수집
# ────────────────────────────────────────────────────────────────────────


def _resolve_master(agent: Any) -> tuple[str | None, str | None, str | None]:
    """HwarangAgent 인스턴스에서 master_url / agent_id / api_key 추출."""
    master = getattr(agent, "master_url", None)
    agent_id = getattr(agent, "agent_id", None)
    api_key = getattr(agent, "api_key", None) or os.environ.get("HWARANG_AGENT_KEY")
    return master, agent_id, api_key


async def collect_state(agent: Any) -> dict[str, Any]:
    """HwarangAgent 에서 모든 상태를 모아 dict 반환."""
    state = default_state()

    # 기본 상태
    running = bool(getattr(agent, "running", False))
    hfl_active = bool(getattr(agent, "hfl_active", False))
    if not running:
        state["status"] = "stopped"
    elif hfl_active:
        state["status"] = "running"
    else:
        state["status"] = "idle"

    # uptime
    started_at = getattr(agent, "_started_at", None)
    if started_at:
        try:
            uptime = (datetime.now(timezone.utc) - started_at).total_seconds() / 60
            state["uptime_minutes"] = int(uptime)
        except Exception:
            pass

    # 마지막 에러
    last_err = getattr(agent, "last_error", None)
    if last_err:
        state["last_error"] = str(last_err)
        if state["status"] == "idle":
            state["status"] = "error"

    # 연결 여부 — http client 존재 + master 응답 가능
    state["connected"] = bool(getattr(agent, "_http_client", None) or running)

    # GPU
    state.update(_gpu_state())

    # 활성 라운드
    state.update(_round_state())

    # 마스터 통신 필요 항목
    master, agent_id, api_key = _resolve_master(agent)
    earnings = await _earnings_state(master, agent_id, api_key)
    profile = await _profile_state(master, agent_id, api_key)
    state.update(earnings)
    state.update(profile)

    return state


# ────────────────────────────────────────────────────────────────────────
# 백그라운드 루프
# ────────────────────────────────────────────────────────────────────────


async def status_writer_loop(
    get_state_fn: Callable[[], Awaitable[dict[str, Any]]],
    interval_sec: int = 30,
    stop_event: asyncio.Event | None = None,
) -> None:
    """주기적으로 get_state_fn() 호출 → write_status().

    Args:
        get_state_fn: async function → 상태 dict
        interval_sec: 갱신 간격 (기본 30초)
        stop_event:   설정되면 즉시 종료
    """
    if stop_event is None:
        stop_event = asyncio.Event()

    logger.info("status_writer_loop 시작 (interval=%ds)", interval_sec)
    while not stop_event.is_set():
        try:
            state = await get_state_fn()
            await write_status(state)
        except Exception as exc:
            logger.warning("status_writer_loop iteration 실패: %s", exc)
            try:
                await write_status({"status": "error", "last_error": str(exc)})
            except Exception:
                pass

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_sec)
        except asyncio.TimeoutError:
            continue

    # 종료 시 stopped 상태 기록
    try:
        await write_status({"status": "stopped"})
    except Exception:
        pass
    logger.info("status_writer_loop 종료")


__all__ = [
    "status_path",
    "default_state",
    "write_status",
    "write_status_sync",
    "collect_state",
    "status_writer_loop",
]
