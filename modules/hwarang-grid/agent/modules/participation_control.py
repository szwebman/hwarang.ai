"""참여 제어

round_subscription.py 의 판단 결과를 받아 실제 join/decline/pause 를 집행한다.

책임:
    - 라운드 join/decline API 호출
    - 동시 실행 중인 라운드 상태 추적 (_active_rounds)
    - 일시 중단 (게이밍/다른 작업 시)
    - heartbeat 전송 (마스터가 에이전트 생존 확인)
    - 긴급 중단 (OOM/과열)

에이전트는 PARTICIPANT — 스스로 라운드를 만들지 않는다.
모든 엔드포인트는 /api/grid/... 통일.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    import httpx  # type: ignore
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

try:
    from .gpu_detector import detect_gpu, get_gpu_metrics  # type: ignore
except Exception:  # pragma: no cover
    detect_gpu = None  # type: ignore
    get_gpu_metrics = None  # type: ignore

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# 상태
# ----------------------------------------------------------------------------


@dataclass
class ActiveRound:
    """현재 이 에이전트가 참여 중인 라운드."""

    round_id: str
    joined_at: datetime
    status: str  # 'joined' | 'training' | 'uploading' | 'completed' | 'failed' | 'aborted'
    progress: float = 0.0
    vram_used_gb: float = 0.0
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None


# 모듈 전역 상태 (에이전트 프로세스당 1개)
_active_rounds: dict[str, ActiveRound] = {}
_paused_until: datetime | None = None
_state_lock = asyncio.Lock()


# ----------------------------------------------------------------------------
# 일시 중단
# ----------------------------------------------------------------------------


async def pause_participation(duration_minutes: int = 60) -> datetime:
    """일시 중단 (게이밍/타 작업 시).

    현재 실행 중인 라운드는 계속 진행되나,
    새 라운드 join 은 모두 거부.
    """
    global _paused_until
    async with _state_lock:
        _paused_until = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
    logger.warning("참여 일시 중단 until %s", _paused_until.isoformat())
    return _paused_until


async def resume_participation() -> None:
    """일시 중단 해제."""
    global _paused_until
    async with _state_lock:
        _paused_until = None
    logger.info("참여 재개")


def is_paused() -> bool:
    """현재 일시 중단 중인지."""
    global _paused_until
    if _paused_until is None:
        return False
    if datetime.now(timezone.utc) >= _paused_until:
        # 자동 해제
        _paused_until = None
        return False
    return True


def paused_until() -> datetime | None:
    return _paused_until


# ----------------------------------------------------------------------------
# 활성 라운드 등록/갱신
# ----------------------------------------------------------------------------


async def register_active_round(round_id: str) -> None:
    """라운드 join 직후 활성 목록에 등록."""
    async with _state_lock:
        _active_rounds[round_id] = ActiveRound(
            round_id=round_id,
            joined_at=datetime.now(timezone.utc),
            status="joined",
        )
    logger.info("활성 라운드 등록: %s", round_id)


async def update_round_progress(
    round_id: str,
    progress: float,
    status: str = "training",
    vram_used_gb: float | None = None,
) -> None:
    """진행률 업데이트."""
    async with _state_lock:
        r = _active_rounds.get(round_id)
        if r is None:
            logger.warning("알 수 없는 라운드 진행률 업데이트: %s", round_id)
            return
        r.progress = max(0.0, min(1.0, progress))
        r.status = status
        r.last_update = datetime.now(timezone.utc)
        if vram_used_gb is not None:
            r.vram_used_gb = vram_used_gb


async def complete_round(round_id: str, success: bool = True, error: str | None = None) -> None:
    """라운드 완료 처리 — 활성 목록에서 제거."""
    async with _state_lock:
        r = _active_rounds.pop(round_id, None)
    if r is None:
        logger.warning("complete_round: 알 수 없는 라운드 %s", round_id)
        return
    duration = (datetime.now(timezone.utc) - r.joined_at).total_seconds() / 60
    if success:
        logger.info("라운드 완료: %s (%.1f분 소요)", round_id, duration)
    else:
        logger.error("라운드 실패: %s (%.1f분 소요, error=%s)", round_id, duration, error)


def list_active_rounds() -> list[dict[str, Any]]:
    """활성 라운드 목록 (모니터링용)."""
    out = []
    for r in _active_rounds.values():
        d = asdict(r)
        # datetime → isoformat
        d["joined_at"] = r.joined_at.isoformat()
        d["last_update"] = r.last_update.isoformat()
        out.append(d)
    return out


def can_accept_new_round(profile_max_concurrent: int) -> bool:
    """동시 실행 한도 체크 + 일시 중단 체크."""
    if is_paused():
        return False
    return len(_active_rounds) < max(1, profile_max_concurrent)


# ----------------------------------------------------------------------------
# 시스템 부하
# ----------------------------------------------------------------------------


async def get_current_load() -> dict[str, Any]:
    """GPU/CPU/메모리 현재 사용률.

    system_monitor.py 의존성을 피하기 위해 gpu_detector + psutil 을 직접 사용.
    """
    result: dict[str, Any] = {
        "gpu": {"usage_percent": 0.0, "vram_used_gb": 0.0, "vram_total_gb": 0.0, "temp_c": 0},
        "cpu": {"percent": 0.0},
        "memory": {"used_pct": 0.0},
        "disk": {"used_pct": 0.0},
    }

    # GPU
    if get_gpu_metrics is not None:
        try:
            m = get_gpu_metrics() or {}
            result["gpu"] = {
                "usage_percent": float(m.get("usage_percent", 0) or 0),
                "vram_used_gb": float(m.get("vram_used_gb", 0) or 0),
                "vram_total_gb": float(m.get("vram_total_gb", 0) or 0),
                "temp_c": int(m.get("temp_c", 0) or 0),
                "power_w": int(m.get("power_w", 0) or 0),
            }
        except Exception as e:
            logger.debug("GPU 메트릭 수집 실패: %s", e)

    # CPU/메모리/디스크
    try:
        import psutil  # type: ignore
        result["cpu"]["percent"] = psutil.cpu_percent()
        result["memory"]["used_pct"] = psutil.virtual_memory().percent
        result["disk"]["used_pct"] = psutil.disk_usage("/").percent
    except Exception:
        pass

    return result


# ----------------------------------------------------------------------------
# 마스터 호출
# ----------------------------------------------------------------------------


async def _post(
    url: str,
    api_key: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 15.0,
) -> dict[str, Any] | None:
    """내부 POST 헬퍼."""
    if httpx is None:
        logger.warning("httpx 미설치 — 요청 스킵: %s", url)
        return None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload or {}, headers=headers)
            resp.raise_for_status()
            if resp.headers.get("content-type", "").startswith("application/json"):
                return resp.json()
            return {}
    except Exception as e:
        logger.error("POST 실패 %s: %s", url, e)
        return None


async def join_round(
    master_url: str,
    agent_id: str,
    api_key: str,
    round_id: str,
) -> dict[str, Any]:
    """POST /api/grid/rounds/{round_id}/join

    성공 시 활성 라운드 등록.
    """
    if is_paused():
        logger.warning("일시 중단 중 — join 거부: %s", round_id)
        return {"ok": False, "error": "paused"}

    url = f"{master_url.rstrip('/')}/api/grid/rounds/{round_id}/join"
    payload = {"agent_id": agent_id, "joined_at": datetime.now(timezone.utc).isoformat()}
    resp = await _post(url, api_key, payload)
    if resp is None:
        return {"ok": False, "error": "network"}

    await register_active_round(round_id)
    logger.info("라운드 join 성공: %s", round_id)
    return {"ok": True, "round_id": round_id, "response": resp}


async def decline_round(
    master_url: str,
    agent_id: str,
    api_key: str,
    round_id: str,
    reason: str,
) -> None:
    """POST /api/grid/rounds/{round_id}/decline"""
    url = f"{master_url.rstrip('/')}/api/grid/rounds/{round_id}/decline"
    payload = {"agent_id": agent_id, "reason": reason}
    await _post(url, api_key, payload)
    logger.info("라운드 decline: %s — %s", round_id, reason)


async def heartbeat_to_master(
    master_url: str,
    agent_id: str,
    api_key: str,
) -> dict[str, Any] | None:
    """POST /api/grid/agents/{agent_id}/heartbeat

    현재 활성 라운드 + 리소스 상태 전송.
    """
    url = f"{master_url.rstrip('/')}/api/grid/agents/{agent_id}/heartbeat"
    load = await get_current_load()
    payload = {
        "agent_id": agent_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "paused": is_paused(),
        "paused_until": _paused_until.isoformat() if _paused_until else None,
        "active_rounds": list_active_rounds(),
        "load": load,
    }
    return await _post(url, api_key, payload, timeout=10.0)


async def heartbeat_loop(
    master_url: str,
    agent_id: str,
    api_key: str,
    interval_seconds: int = 30,
    stop_event: asyncio.Event | None = None,
) -> None:
    """주기적 heartbeat."""
    stop_event = stop_event or asyncio.Event()
    logger.info("heartbeat_loop 시작 (interval=%ds)", interval_seconds)
    while not stop_event.is_set():
        try:
            await heartbeat_to_master(master_url, agent_id, api_key)
        except Exception as e:
            logger.debug("heartbeat 오류: %s", e)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass
    logger.info("heartbeat_loop 종료")


# ----------------------------------------------------------------------------
# 긴급 중단
# ----------------------------------------------------------------------------


async def emergency_abort(
    round_id: str,
    reason: str,
    master_url: str | None = None,
    agent_id: str | None = None,
    api_key: str | None = None,
    partial_metrics: dict[str, Any] | None = None,
) -> None:
    """긴급 중단 (OOM/과열 등). 부분 결과도 전송 시도."""
    logger.error("긴급 중단: round_id=%s, reason=%s", round_id, reason)

    # 상태 업데이트
    async with _state_lock:
        r = _active_rounds.get(round_id)
        if r:
            r.status = "aborted"
            r.error = reason
            r.last_update = datetime.now(timezone.utc)

    # 마스터에 통보
    if master_url and agent_id and api_key:
        url = f"{master_url.rstrip('/')}/api/grid/rounds/{round_id}/abort"
        payload = {
            "agent_id": agent_id,
            "reason": reason,
            "partial_metrics": partial_metrics or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await _post(url, api_key, payload, timeout=5.0)

    await complete_round(round_id, success=False, error=reason)


# ----------------------------------------------------------------------------
# 과열/OOM 자동 감시
# ----------------------------------------------------------------------------


async def check_thermal_safety(
    round_id: str,
    temp_limit_c: int = 85,
    master_url: str | None = None,
    agent_id: str | None = None,
    api_key: str | None = None,
) -> bool:
    """GPU 온도가 임계치를 넘으면 긴급 중단. True = 안전, False = 중단됨."""
    load = await get_current_load()
    temp = load.get("gpu", {}).get("temp_c", 0)
    if temp and temp >= temp_limit_c:
        await emergency_abort(
            round_id,
            f"GPU 과열 {temp}°C >= 한계 {temp_limit_c}°C",
            master_url=master_url,
            agent_id=agent_id,
            api_key=api_key,
            partial_metrics={"gpu_temp_c": temp},
        )
        return False
    return True


# ----------------------------------------------------------------------------
# CLI 테스트
# ----------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")

    async def main():
        await register_active_round("r-test-1")
        await update_round_progress("r-test-1", 0.3, status="training", vram_used_gb=12.0)
        print("활성 라운드:", list_active_rounds())
        print("현재 부하:", await get_current_load())
        print("일시 중단?", is_paused())
        await pause_participation(1)
        print("일시 중단?", is_paused())
        await resume_participation()
        print("일시 중단?", is_paused())
        await complete_round("r-test-1", success=True)

    asyncio.run(main())
