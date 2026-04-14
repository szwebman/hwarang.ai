"""API Versioning - 무중단 API 버전 관리.

/v1/chat/completions → /v2/chat/completions 전환 시
기존 사용자는 v1 계속 사용, 새 사용자는 v2 사용.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)


class APIVersionManager:
    """API 버전 관리."""

    def __init__(self):
        self._versions: dict[str, APIRouter] = {}
        self._default_version = "v1"
        self._deprecated: set[str] = set()

    def register_version(self, version: str, router: APIRouter):
        self._versions[version] = router

    def deprecate_version(self, version: str):
        self._deprecated.add(version)
        logger.info(f"API {version} deprecated")

    def get_router(self, version: str) -> APIRouter | None:
        return self._versions.get(version)

    def is_deprecated(self, version: str) -> bool:
        return version in self._deprecated

    @property
    def available_versions(self) -> list[str]:
        return list(self._versions.keys())

    def get_deprecation_header(self, version: str) -> dict:
        """Deprecated 버전이면 경고 헤더 반환."""
        if self.is_deprecated(version):
            return {
                "X-API-Deprecated": "true",
                "X-API-Sunset": "2027-01-01",
                "X-API-Latest": self._default_version,
            }
        return {}
