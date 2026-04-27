"""PID 파일 관리.

데몬 모드에서 다중 실행 방지 + graceful shutdown 지원.

경로: ~/.hwarang/agent.pid

사용 예:
    from modules.pid_manager import write_pid, remove_pid, is_running

    if is_running():
        print("이미 실행 중")
        sys.exit(1)
    write_pid()
    try:
        run_agent()
    finally:
        remove_pid()
"""

from __future__ import annotations

import logging
import os
import signal
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# 선택적 의존성 — 없으면 signal-0 폴백
try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore


# ────────────────────────────────────────────────────────────────────────
# 경로
# ────────────────────────────────────────────────────────────────────────

HOME_DIR = Path.home() / ".hwarang"
PID_FILE = HOME_DIR / "agent.pid"


def pid_path() -> Path:
    """PID 파일 경로 (~/.hwarang/agent.pid)."""
    return PID_FILE


def _ensure_dir() -> None:
    HOME_DIR.mkdir(parents=True, exist_ok=True)


# ────────────────────────────────────────────────────────────────────────
# 읽기 / 쓰기 / 삭제
# ────────────────────────────────────────────────────────────────────────


def write_pid(pid: int | None = None) -> Path:
    """현재(또는 지정된) PID 를 파일에 기록."""
    _ensure_dir()
    pid = pid if pid is not None else os.getpid()
    PID_FILE.write_text(f"{pid}\n", encoding="utf-8")
    logger.info("PID 기록: %s → %s", pid, PID_FILE)
    return PID_FILE


def read_pid() -> int | None:
    """PID 파일에서 PID 읽기. 없거나 손상되면 None."""
    if not PID_FILE.exists():
        return None
    try:
        text = PID_FILE.read_text(encoding="utf-8").strip()
        if not text:
            return None
        return int(text.split()[0])
    except Exception as exc:
        logger.warning("PID 파일 파싱 실패: %s", exc)
        return None


def remove_pid() -> None:
    """PID 파일 삭제 (없어도 무시)."""
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
            logger.info("PID 파일 제거: %s", PID_FILE)
    except Exception as exc:
        logger.warning("PID 파일 제거 실패: %s", exc)


# ────────────────────────────────────────────────────────────────────────
# 실행 여부 확인
# ────────────────────────────────────────────────────────────────────────


def _pid_alive(pid: int) -> bool:
    """주어진 PID가 살아있는지."""
    if pid <= 0:
        return False
    if psutil is not None:
        try:
            proc = psutil.Process(pid)
            # zombie 도 false 처리
            if proc.status() == getattr(psutil, "STATUS_ZOMBIE", "zombie"):
                return False
            return proc.is_running()
        except Exception:
            return False

    # psutil 없을 때: signal 0
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # 권한 없어도 프로세스 자체는 존재
        return True
    except Exception:
        return False


def is_running() -> bool:
    """PID 파일 기준으로 데몬이 실행 중인지."""
    pid = read_pid()
    if pid is None:
        return False
    if pid == os.getpid():
        # 자신의 PID — 호출자 컨텍스트에선 True 로 간주
        return True
    return _pid_alive(pid)


def is_stale() -> bool:
    """PID 파일은 있지만 프로세스가 죽은 상태인지."""
    pid = read_pid()
    return pid is not None and pid != os.getpid() and not _pid_alive(pid)


def cleanup_stale() -> bool:
    """stale PID 파일이 있으면 제거. 제거되었으면 True."""
    if is_stale():
        logger.warning("stale PID 파일 감지 → 제거: %s", PID_FILE)
        remove_pid()
        return True
    return False


# ────────────────────────────────────────────────────────────────────────
# 종료
# ────────────────────────────────────────────────────────────────────────


def stop_running_agent(timeout_sec: int = 10) -> bool:
    """현재 PID 파일에 기록된 데몬에 SIGTERM → wait → SIGKILL.

    Returns:
        True  — 종료 성공 (또는 처음부터 실행 중이 아니었음)
        False — SIGKILL 까지 보냈는데도 살아있음
    """
    pid = read_pid()
    if pid is None:
        logger.info("실행 중인 에이전트 없음 (PID 파일 없음)")
        return True
    if not _pid_alive(pid):
        logger.info("PID %s 는 이미 종료됨 → PID 파일만 정리", pid)
        remove_pid()
        return True

    logger.info("SIGTERM 송신 → PID %s", pid)
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception as exc:
        logger.warning("SIGTERM 실패: %s", exc)

    deadline = time.time() + max(1, timeout_sec)
    while time.time() < deadline:
        if not _pid_alive(pid):
            logger.info("graceful shutdown 완료 (PID %s)", pid)
            remove_pid()
            return True
        time.sleep(0.3)

    logger.warning("SIGTERM 타임아웃 → SIGKILL 송신 (PID %s)", pid)
    try:
        os.kill(pid, signal.SIGKILL)
    except Exception as exc:
        logger.warning("SIGKILL 실패: %s", exc)
        return False

    # SIGKILL 후 짧게 대기
    time.sleep(0.5)
    alive = _pid_alive(pid)
    if not alive:
        remove_pid()
        return True
    logger.error("PID %s 종료 실패 (살아있음)", pid)
    return False


__all__ = [
    "pid_path",
    "write_pid",
    "read_pid",
    "remove_pid",
    "is_running",
    "is_stale",
    "cleanup_stale",
    "stop_running_agent",
]
