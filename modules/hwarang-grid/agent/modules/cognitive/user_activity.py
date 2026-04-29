"""OS별 사용자 활동(idle) 감지.

마우스/키보드 마지막 입력 후 경과 시간을 초 단위로 반환.

플랫폼
------
* macOS  — ``ioreg -c IOHIDSystem`` 의 ``HIDIdleTime`` (나노초)
* Linux  — ``xprintidle`` (밀리초). Wayland / 헤드리스에서는 폴백.
* Windows — ``GetLastInputInfo`` (밀리초, ctypes/wintypes)

폴백 정책
---------
감지 실패 시 ``999.0`` 초 반환 — "사용자 없음(자리 비움)" 으로 간주해
GPU 사용을 막지 않는 보수적 기본값. (이전 stub 은 피크시간대 = 활동중으로
보수 추정해 야간 GPU 사용을 차단했음.)

캐시
----
``ioreg``/``xprintidle`` 호출이 매 호출마다 0.05~0.2초 걸릴 수 있어
0.5초 캐시를 둠. ``state_collector`` 가 짧은 간격으로 호출해도 안전.
"""

from __future__ import annotations

import logging
import platform
import subprocess
import time
from typing import Optional

logger = logging.getLogger(__name__)

# 캐시 — (ts, idle_seconds)
_CACHE_TTL = 0.5
_cache: tuple[float, float] | None = None


def _cached_or(get: callable) -> float:
    """짧은 캐시 — 같은 idle 값을 반복 호출에 재사용."""
    global _cache
    now = time.time()
    if _cache and now - _cache[0] < _CACHE_TTL:
        return _cache[1]
    val = get()
    _cache = (now, val)
    return val


def get_idle_seconds() -> float:
    """마지막 사용자 입력 후 경과 초.

    실패 시 ``999.0`` (자리 비움 가정 — GPU 사용 허용).
    """
    system = platform.system()

    def _impl() -> float:
        try:
            if system == "Darwin":
                return _macos_idle()
            if system == "Linux":
                return _linux_idle()
            if system == "Windows":
                return _windows_idle()
        except Exception as exc:
            logger.debug("idle 감지 실패 (%s): %s", system, exc)
        return 999.0

    return _cached_or(_impl)


def _macos_idle() -> float:
    """macOS — ``ioreg -c IOHIDSystem`` 의 HIDIdleTime (ns)."""
    try:
        output = subprocess.check_output(
            ["ioreg", "-c", "IOHIDSystem"],
            timeout=3,
            stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="ignore")
    except (FileNotFoundError, subprocess.SubprocessError):
        return 999.0

    for line in output.splitlines():
        if "HIDIdleTime" in line:
            try:
                # '"HIDIdleTime" = 12345678901'
                ns = int(line.split("=", 1)[1].strip())
                return ns / 1_000_000_000.0
            except (ValueError, IndexError):
                continue
    return 999.0


def _linux_idle() -> float:
    """Linux — ``xprintidle`` (ms). Wayland/헤드리스 미지원."""
    try:
        out = subprocess.check_output(
            ["xprintidle"],
            timeout=3,
            stderr=subprocess.DEVNULL,
        ).decode("utf-8").strip()
        return int(out) / 1000.0
    except FileNotFoundError:
        # xprintidle 미설치 — apt install xprintidle 권장
        return 999.0
    except subprocess.SubprocessError:
        return 999.0
    except ValueError:
        return 999.0


def _windows_idle() -> float:
    """Windows — ``GetLastInputInfo`` 로 마지막 입력 tick 조회."""
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return 999.0

    class LASTINPUTINFO(ctypes.Structure):  # noqa: N801
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("dwTime", wintypes.DWORD),
        ]

    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    except Exception:
        return 999.0

    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not user32.GetLastInputInfo(ctypes.byref(lii)):
        return 999.0

    millis = kernel32.GetTickCount() - lii.dwTime
    if millis < 0:
        return 0.0
    return millis / 1000.0


def is_user_active(threshold_seconds: int = 60) -> bool:
    """사용자가 최근 ``threshold_seconds`` 초 안에 활동했나."""
    return get_idle_seconds() < float(threshold_seconds)


def get_idle_state() -> dict:
    """idle 상태 + 카테고리 — state_collector / 마스터 보고용.

    카테고리:
        active  — < 60초 (사용자 입력 중)
        recent  — < 5분 (방금 떠남)
        idle    — < 15분
        away    — ≥ 15분 (안전하게 GPU 사용 가능)
    """
    idle_sec = get_idle_seconds()

    if idle_sec < 60:
        category = "active"
    elif idle_sec < 300:
        category = "recent"
    elif idle_sec < 900:
        category = "idle"
    else:
        category = "away"

    return {
        "idle_seconds": idle_sec,
        "category": category,
        "is_active": idle_sec < 60,
        # 5분 이상 자리비움 = GPU 풀가동 OK (사용자 방해 X)
        "is_safe_to_use_gpu": idle_sec >= 300,
        "platform": platform.system(),
    }


__all__ = [
    "get_idle_seconds",
    "is_user_active",
    "get_idle_state",
]
