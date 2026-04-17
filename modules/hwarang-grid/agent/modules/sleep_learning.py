"""Sleep Learning - 수면 학습 (세계 최초)

PC 유휴 상태 자동 감지 → GPU 풀파워 학습.
사람이 자는 동안 AI가 학습하고 코인을 번다.

동작:
  1. 마우스/키보드 N분 미입력 → 유휴 판정
  2. 화면보호기/화면꺼짐 감지
  3. GPU 풀파워 학습 시작
  4. 마우스/키보드 입력 감지 → 즉시 중단, GPU 반환
  5. 학습 결과 + 증명 → 마스터 제출 → 코인 보상

설정:
  idle_threshold_min: 유휴 판정 시간 (기본 5분)
  max_gpu_percent: 수면 학습 시 GPU 사용률 (기본 90%)
  resume_delay_sec: 유저 복귀 후 GPU 반환 지연 (기본 3초)
  quiet_hours: 수면 시간 강제 (예: 23:00~07:00)
"""

import time
import threading
import logging
import os
import platform

logger = logging.getLogger(__name__)


class IdleDetector:
    """시스템 유휴 상태 감지."""

    @staticmethod
    def get_idle_seconds() -> float:
        """마지막 입력 이후 경과 시간 (초)."""
        system = platform.system()

        if system == "Windows":
            return IdleDetector._windows_idle()
        elif system == "Darwin":  # macOS
            return IdleDetector._macos_idle()
        elif system == "Linux":
            return IdleDetector._linux_idle()
        return 0

    @staticmethod
    def _windows_idle() -> float:
        try:
            import ctypes

            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return millis / 1000
        except:
            return 0

    @staticmethod
    def _macos_idle() -> float:
        try:
            import subprocess
            result = subprocess.run(
                ["ioreg", "-c", "IOHIDSystem", "-d", "4"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.split("\n"):
                if "HIDIdleTime" in line:
                    ns = int(line.split("=")[-1].strip())
                    return ns / 1_000_000_000
        except:
            pass
        return 0

    @staticmethod
    def _linux_idle() -> float:
        try:
            import subprocess
            result = subprocess.run(
                ["xprintidle"], capture_output=True, text=True, timeout=5,
            )
            return int(result.stdout.strip()) / 1000
        except:
            # X11 없는 서버 환경
            return 999999  # 항상 유휴 (서버는 24시간 가동)

    @staticmethod
    def is_screen_off() -> bool:
        """화면 꺼짐 감지."""
        system = platform.system()
        if system == "Linux":
            try:
                import subprocess
                result = subprocess.run(
                    ["xset", "q"], capture_output=True, text=True, timeout=3,
                )
                return "Monitor is Off" in result.stdout
            except:
                return False
        return False


class SleepLearningModule:
    """수면 학습 모듈."""

    def __init__(self, config=None):
        self.idle_threshold_sec = (config.idle_threshold_min if config else 5) * 60
        self.max_gpu_percent = config.max_gpu_percent if config else 0.9
        self.resume_delay_sec = config.resume_delay_sec if config else 3
        self.is_sleeping = False
        self.total_sleep_hours = 0
        self.total_steps_learned = 0
        self.sessions = []
        self._stop_event = threading.Event()

    def start_monitor(self, on_sleep_start, on_sleep_end):
        """유휴 상태 모니터링 시작.

        Args:
            on_sleep_start: 수면 모드 진입 콜백 → GPU 학습 시작
            on_sleep_end: 수면 모드 해제 콜백 → GPU 반환
        """
        def _loop():
            while not self._stop_event.is_set():
                idle_sec = IdleDetector.get_idle_seconds()

                if not self.is_sleeping and idle_sec >= self.idle_threshold_sec:
                    # 유휴 감지 → 수면 학습 시작
                    self.is_sleeping = True
                    session_start = time.time()
                    logger.info(f"😴 수면 학습 시작 (유휴 {idle_sec:.0f}초)")

                    try:
                        on_sleep_start(gpu_percent=self.max_gpu_percent)
                    except Exception as e:
                        logger.error(f"수면 학습 시작 실패: {e}")

                elif self.is_sleeping and idle_sec < self.resume_delay_sec:
                    # 유저 복귀 감지 → 즉시 중단
                    self.is_sleeping = False
                    duration = time.time() - session_start
                    self.total_sleep_hours += duration / 3600

                    logger.info(
                        f"🌅 수면 학습 종료 (시간 {duration/3600:.1f}시간, "
                        f"누적 {self.total_sleep_hours:.1f}시간)"
                    )

                    self.sessions.append({
                        "start": session_start,
                        "duration_hours": round(duration / 3600, 2),
                        "gpu_percent": self.max_gpu_percent,
                    })

                    try:
                        on_sleep_end()
                    except Exception as e:
                        logger.error(f"수면 학습 종료 실패: {e}")

                time.sleep(10)  # 10초마다 체크

        thread = threading.Thread(target=_loop, name="sleep-learning", daemon=True)
        thread.start()
        logger.info(f"수면 학습 모니터 시작 (유휴 임계 {self.idle_threshold_sec}초)")

    def stop(self):
        self._stop_event.set()

    def get_stats(self) -> dict:
        return {
            "is_sleeping": self.is_sleeping,
            "total_sleep_hours": round(self.total_sleep_hours, 1),
            "total_sessions": len(self.sessions),
            "idle_threshold_sec": self.idle_threshold_sec,
            "max_gpu_percent": self.max_gpu_percent,
        }
