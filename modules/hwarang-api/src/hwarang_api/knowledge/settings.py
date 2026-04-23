"""HLKM 런타임 설정 로더/세이버.

`SystemSetting` Prisma 테이블의 `hlkm.*` 키에 값을 JSON 으로 저장한다.
- 스케줄러, 파이프라인, 보상 계산 등이 이 값을 참조한다.
- prisma-client-py 가 없는 환경에서는 기본값만 반환 (silently).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------
SETTING_KEY_PREFIX: str = "hlkm."


# ---------------------------------------------------------------------------
# 모델
# ---------------------------------------------------------------------------
class HLKMSettings(BaseModel):
    """HLKM 전역 운영 파라미터.

    각 필드는 ``SystemSetting`` 테이블에 ``hlkm.<snake_case_field>`` 키로 저장된다.
    """

    # ── 임계치 ─────────────────────────────────────
    contradiction_embed_threshold: float = Field(
        default=0.4,
        description="임베딩 거리 기반 1차 모순 후보 필터 (L2 거리 ≤ threshold → 후보)",
    )
    contradiction_llm_confidence_threshold: float = Field(
        default=0.7,
        description="LLM 판정 신뢰도가 이 이상이면 실제 모순으로 간주",
    )
    auto_approve_quality_threshold: float = Field(
        default=0.9,
        description="큐레이션 품질 점수가 이 이상이면 자동 수집",
    )
    auto_approve_uniqueness_threshold: float = Field(
        default=0.5,
        description="유니크도가 이 이하면 중복으로 간주해 자동 승인 제외",
    )

    # ── 반감기 오버라이드 (도메인 → 일수) ───────────
    half_life_overrides: dict[str, int] = Field(
        default_factory=dict,
        description="DEFAULT_HALF_LIFE 를 덮어쓰는 관리자 설정",
    )

    # ── 스케줄러 토글 ───────────────────────────────
    daily_verify_enabled: bool = True
    hrag_law_sync_enabled: bool = True
    hrag_weather_sync_enabled: bool = True
    hrag_news_sync_enabled: bool = False
    halflife_retrain_enabled: bool = True

    # ── 보상 설정 ──────────────────────────────────
    reward_base_per_domain: dict[str, int] = Field(
        default_factory=lambda: {
            "law": 100,
            "medical": 150,
            "tech": 50,
            "general": 20,
        },
        description="도메인별 기여 기본 보상 (HWARANG 코인 단위)",
    )
    reward_tier_multipliers: dict[str, float] = Field(
        default_factory=lambda: {
            "basic": 1.0,
            "verified": 1.3,
            "expert": 1.8,
        },
        description="기여자 등급별 보상 배수",
    )

    # ── 한도 ──────────────────────────────────────
    max_verifications_per_run: int = Field(
        default=500,
        description="run_daily_verification 1회 실행에서 처리할 최대 팩트 수",
    )
    max_facts_per_user_per_day: int = Field(
        default=100,
        description="1인당 하루 수집 가능한 팩트 수 상한 (스팸 방지)",
    )

    # ── 프라이버시 ─────────────────────────────────
    require_pii_redaction: bool = Field(
        default=True,
        description="공개 팩트 등록 전 PII 자동 차폐 강제",
    )
    private_encryption_enabled: bool = Field(
        default=True,
        description="PRIVATE visibility 팩트의 AES 암호화 활성화",
    )


# ---------------------------------------------------------------------------
# 내부 유틸
# ---------------------------------------------------------------------------
def _camelify(key: str) -> str:
    """``hlkm.foo_bar`` → ``foo_bar`` (prefix 만 제거)."""
    if key.startswith(SETTING_KEY_PREFIX):
        return key[len(SETTING_KEY_PREFIX):]
    return key


def _prefixed(field_name: str) -> str:
    """필드명을 실제 DB 키로 변환."""
    return f"{SETTING_KEY_PREFIX}{field_name}"


def _encode(value: Any) -> str:
    """DB 저장용 JSON 문자열화. 스칼라도 JSON 으로 감싸 역직렬화 일관성 유지."""
    return json.dumps(value, ensure_ascii=False, default=str)


def _decode(raw: str) -> Any:
    """저장된 JSON 문자열을 Python 값으로 복원. 실패하면 원 문자열 반환."""
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


async def _get_prisma():
    """순환 import 방지용 지연 임포트. 실패 시 None."""
    try:
        from hwarang_api.db import prisma  # type: ignore

        # stub 여부 탐지: is_connected 호출로 확인
        if hasattr(prisma, "is_connected") and not prisma.is_connected():
            try:
                await prisma.connect()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                return None
        return prisma
    except Exception as exc:  # noqa: BLE001
        logger.debug("prisma unavailable: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 공용 API
# ---------------------------------------------------------------------------
async def get_settings() -> HLKMSettings:
    """``hlkm.*`` 키 전체를 읽어 기본값과 병합한 :class:`HLKMSettings` 반환.

    - DB 미연결/오류 시 기본값만 담긴 인스턴스를 반환.
    - 알 수 없는 키는 무시 (상위 버전 호환).
    """
    defaults = HLKMSettings()
    client = await _get_prisma()
    if client is None:
        return defaults

    try:
        rows = await client.systemsetting.find_many(
            where={"key": {"startsWith": SETTING_KEY_PREFIX}}
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_settings: DB 조회 실패, 기본값 반환: %s", exc)
        return defaults

    overrides: dict[str, Any] = {}
    known_fields = set(HLKMSettings.model_fields.keys())
    for row in rows:
        field = _camelify(row.key)
        if field not in known_fields:
            continue
        overrides[field] = _decode(row.value)

    if not overrides:
        return defaults

    # pydantic 이 타입 검증을 수행; 실패 필드는 기본값으로 폴백
    try:
        return HLKMSettings(**{**defaults.model_dump(), **overrides})
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_settings: 일부 값이 유효하지 않아 기본값 병합: %s", exc)
        merged = defaults.model_dump()
        for k, v in overrides.items():
            try:
                HLKMSettings(**{**merged, k: v})
                merged[k] = v
            except Exception:  # noqa: BLE001
                logger.debug("무효 필드 무시: %s=%r", k, v)
        return HLKMSettings(**merged)


async def save_settings(new: HLKMSettings) -> None:
    """전체 설정을 DB 에 upsert.

    각 필드마다 별도의 row 를 관리하므로 부분 수정도 안전.
    """
    client = await _get_prisma()
    if client is None:
        logger.warning("save_settings: prisma unavailable, ignoring")
        return

    data = new.model_dump(mode="json")
    for field_name, value in data.items():
        await set_setting(_prefixed(field_name), value, _client=client)


async def get_setting(key: str, default: Any = None) -> Any:
    """단일 키 조회. ``hlkm.`` prefix 자동 부여."""
    full_key = key if key.startswith(SETTING_KEY_PREFIX) else _prefixed(key)
    client = await _get_prisma()
    if client is None:
        return default

    try:
        row = await client.systemsetting.find_unique(where={"key": full_key})
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_setting(%s) 실패: %s", full_key, exc)
        return default

    if row is None:
        return default
    return _decode(row.value)


async def set_setting(key: str, value: Any, *, _client: Any | None = None) -> None:
    """단일 키 upsert. 내부에서 재사용 가능하도록 ``_client`` 주입 허용."""
    full_key = key if key.startswith(SETTING_KEY_PREFIX) else _prefixed(key)
    client = _client if _client is not None else await _get_prisma()
    if client is None:
        logger.warning("set_setting(%s): prisma unavailable", full_key)
        return

    encoded = _encode(value)
    try:
        await client.systemsetting.upsert(
            where={"key": full_key},
            data={
                "create": {"key": full_key, "value": encoded},
                "update": {"value": encoded},
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("set_setting(%s) 실패: %s", full_key, exc)


__all__ = [
    "HLKMSettings",
    "SETTING_KEY_PREFIX",
    "get_settings",
    "save_settings",
    "get_setting",
    "set_setting",
]
