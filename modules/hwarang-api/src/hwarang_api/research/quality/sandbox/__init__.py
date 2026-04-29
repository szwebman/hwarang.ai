"""화랑 코드 샌드박스 — Docker 우선, Firejail 폴백, subprocess 최후 폴백.

격리 우선순위:
  1. Docker 컨테이너 (운영 환경 권장)
  2. Firejail (Linux 전용 가벼운 격리)
  3. subprocess (개발 전용, 격리 약함)

서브 모듈:
  - ``docker_runner``     — Docker 컨테이너 실행
  - ``firejail_runner``   — Firejail 격리 (Linux fallback)
  - ``language_detector`` — 코드 → 언어 식별
  - ``runners/*``         — 언어별 보조 헬퍼
"""

from __future__ import annotations

from .docker_runner import (
    DOCKER_IMAGES,
    SandboxResult,
    is_docker_available,
    run_in_docker,
)
from .firejail_runner import is_firejail_available, run_in_firejail
from .language_detector import detect_language

__all__ = [
    "DOCKER_IMAGES",
    "SandboxResult",
    "detect_language",
    "is_docker_available",
    "is_firejail_available",
    "run_in_docker",
    "run_in_firejail",
]
