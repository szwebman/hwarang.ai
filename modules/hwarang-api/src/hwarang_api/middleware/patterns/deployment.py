"""Deployment Patterns - 배포 패턴.

1. Blue-Green Deploy: 무중단 배포 (v1 → v2)
2. Canary Release: 5% → 20% → 100% 점진적 배포
3. Config Hot Reload: 재시작 없이 설정 변경
4. Secret Management: API 키/비밀번호 안전 관리
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================
# 1. Blue-Green Deploy
# ============================================================

class BlueGreenDeploy:
    """Blue-Green 배포.

    Blue(현재) + Green(새 버전) 동시 운영
    → 테스트 후 트래픽 전환
    → 문제 시 즉시 Blue로 복귀
    """

    def __init__(self):
        self._active = "blue"      # 현재 활성 슬롯
        self._blue_version = ""
        self._green_version = ""

    @property
    def active_slot(self) -> str:
        return self._active

    def deploy_to_inactive(self, version: str) -> str:
        """비활성 슬롯에 새 버전 배포."""
        inactive = "green" if self._active == "blue" else "blue"
        if inactive == "blue":
            self._blue_version = version
        else:
            self._green_version = version
        logger.info(f"Deployed {version} to {inactive} slot")
        return inactive

    def switch(self) -> str:
        """활성 슬롯 전환."""
        old = self._active
        self._active = "green" if self._active == "blue" else "blue"
        logger.info(f"Switched: {old} → {self._active}")
        return self._active

    def rollback(self) -> str:
        """이전 슬롯으로 롤백."""
        return self.switch()

    @property
    def status(self) -> dict:
        return {
            "active": self._active,
            "blue": self._blue_version,
            "green": self._green_version,
        }


# ============================================================
# 2. Canary Release
# ============================================================

class CanaryRelease:
    """Canary 배포 - 점진적 롤아웃.

    새 버전을 일부 트래픽에만 먼저 → 문제 없으면 점진적 확대
    5% → 20% → 50% → 100%
    """

    def __init__(self):
        self._canary_percent: float = 0.0  # 0~100
        self._canary_version: str = ""
        self._stable_version: str = ""
        self._stages = [5, 20, 50, 100]
        self._current_stage = -1

    def start_canary(self, new_version: str, stable_version: str):
        self._canary_version = new_version
        self._stable_version = stable_version
        self._current_stage = 0
        self._canary_percent = self._stages[0]
        logger.info(f"Canary 시작: {new_version} at {self._canary_percent}%")

    def promote(self) -> float:
        """다음 단계로 확대."""
        if self._current_stage < len(self._stages) - 1:
            self._current_stage += 1
            self._canary_percent = self._stages[self._current_stage]
            logger.info(f"Canary 확대: {self._canary_percent}%")
        return self._canary_percent

    def rollback(self):
        """Canary 중단 → 안정 버전으로."""
        logger.info(f"Canary 롤백: {self._canary_version} → {self._stable_version}")
        self._canary_percent = 0
        self._current_stage = -1
        self._canary_version = ""

    def route(self, user_id: str) -> str:
        """유저를 어느 버전으로 보낼지."""
        if self._canary_percent <= 0 or not self._canary_version:
            return self._stable_version

        # 유저 ID 기반 결정 (같은 유저 = 같은 버전)
        h = int(hashlib.md5(user_id.encode()).hexdigest(), 16) % 100
        if h < self._canary_percent:
            return self._canary_version
        return self._stable_version

    @property
    def status(self) -> dict:
        return {
            "canary_version": self._canary_version,
            "stable_version": self._stable_version,
            "canary_percent": self._canary_percent,
            "stage": self._current_stage,
        }


# ============================================================
# 3. Config Hot Reload
# ============================================================

class ConfigHotReloader:
    """서버 재시작 없이 설정 변경.

    설정 파일을 주기적으로 감시 → 변경 감지 → 자동 리로드.
    """

    def __init__(self, config_path: str, check_interval: float = 10.0):
        self.config_path = Path(config_path)
        self.check_interval = check_interval
        self._last_hash: str = ""
        self._config: dict = {}
        self._callbacks: list[callable] = []

    def on_change(self, callback: callable):
        """설정 변경 시 호출할 콜백 등록."""
        self._callbacks.append(callback)

    def load(self) -> dict:
        """설정 로드."""
        if not self.config_path.exists():
            return {}

        content = self.config_path.read_text()
        current_hash = hashlib.md5(content.encode()).hexdigest()

        if current_hash != self._last_hash:
            self._last_hash = current_hash
            if self.config_path.suffix in (".yaml", ".yml"):
                import yaml
                self._config = yaml.safe_load(content) or {}
            else:
                self._config = json.loads(content)

            # 변경 콜백 호출
            for cb in self._callbacks:
                try:
                    cb(self._config)
                except Exception as e:
                    logger.error(f"Config reload callback error: {e}")

            logger.info(f"Config reloaded: {self.config_path}")

        return self._config

    async def watch(self):
        """비동기로 파일 감시."""
        import asyncio
        while True:
            self.load()
            await asyncio.sleep(self.check_interval)

    @property
    def config(self) -> dict:
        return self._config


# ============================================================
# 4. Secret Management
# ============================================================

class SecretManager:
    """API 키/비밀번호 안전 관리.

    우선순위: 환경변수 > .env 파일 > 설정 파일
    절대로 코드나 로그에 시크릿을 노출하지 않음.
    """

    def __init__(self, env_file: str = ".env"):
        self._secrets: dict[str, str] = {}
        self._load_env_file(env_file)

    def _load_env_file(self, path: str):
        """dotenv 파일 로드."""
        p = Path(path)
        if not p.exists():
            return
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                self._secrets[key.strip()] = value.strip().strip('"').strip("'")

    def get(self, key: str, default: str = "") -> str:
        """시크릿 조회 (환경변수 우선)."""
        return os.environ.get(key) or self._secrets.get(key, default)

    def set(self, key: str, value: str):
        """런타임 시크릿 설정."""
        self._secrets[key] = value

    def mask(self, text: str) -> str:
        """텍스트에서 시크릿을 마스킹 (로그 출력용)."""
        masked = text
        for key, value in self._secrets.items():
            if value and len(value) > 4:
                masked = masked.replace(value, f"{value[:4]}****")
        return masked

    @property
    def keys(self) -> list[str]:
        """등록된 시크릿 키 목록 (값은 노출 안 함)."""
        return list(set(list(self._secrets.keys()) + [
            k for k in os.environ if k.startswith("HWARANG_")
        ]))
