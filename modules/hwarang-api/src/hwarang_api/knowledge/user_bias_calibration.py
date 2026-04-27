"""HLKM TAL ⑤ — User Bias Calibration (사용자 편향 캘리브레이션).

사용자가 **자신이 선호하는 편향 스펙트럼** 을 직접 설정할 수 있게 하되,
절대로 필터 버블/에코 챔버로 빠지지 않도록 **가드레일** 을 강제한다.

핵심 원칙:
    1. **사용자 자율**: 진보/중도/보수 선호를 스스로 선택.
    2. **극단 차단**: ``toleranceRange`` 는 최대 0.6 (1.0 = 완전 극단) 까지만.
    3. **반대 관점 노출 보장**: guardrail=balanced 면 반대 비율 ≥ 30% 강제.
    4. **필터 버블 경고**: 최근 피드백이 한쪽으로 쏠리면 자동 경고.
    5. **guardrail=off 는 관리자 전용**: 일반 사용자는 못 끈다.

의존:
    - :mod:`hwarang_api.db.prisma`
    - :class:`.types.KnowledgeFact`
    - :func:`.bias_detection.score_to_label`
    - :func:`.counter_evidence.find_stance_diverse_facts`
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma

from .bias_detection import score_to_label
from .counter_evidence import find_stance_diverse_facts
from .types import KnowledgeFact

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 기본값 / 정책
# ─────────────────────────────────────────────────────────────
DEFAULT_CALIBRATION: dict[str, Any] = {
    "preferredSpectrum": "centrist",       # progressive / moderate / centrist / conservative
    "toleranceRange": 0.3,                 # 0 ~ 1 (선호 스펙트럼 주변 허용 반경)
    "showOpposing": True,
    "guardrailMode": "balanced",           # off / balanced / strict
    "preferences": {
        "politics": {},
        "medical": {},
    },
}


# guardrail 정책: 표시 필터링 / 극단 차단 규칙
GUARDRAIL_POLICIES: dict[str, dict[str, Any]] = {
    "off": {
        "min_opposing_ratio": 0.0,
        "block_extreme": False,
        "excluded_labels": [],
    },
    "balanced": {
        "min_opposing_ratio": 0.3,
        "block_extreme": False,
        "excluded_labels": [],
    },
    "strict": {
        "min_opposing_ratio": 0.4,
        "block_extreme": True,
        "excluded_labels": ["FAR_LEFT", "FAR_RIGHT"],
    },
}


_VALID_SPECTRUMS = {"progressive", "moderate", "centrist", "conservative"}
_VALID_GUARDRAILS = set(GUARDRAIL_POLICIES.keys())
_MAX_USER_TOLERANCE = 0.6  # 사용자 상한. admin 도 이 값을 넘기면 경고.

# 선호 스펙트럼 ↔ 허용 라벨 매핑 (중심값 기준)
_SPECTRUM_TO_LABELS: dict[str, set[str]] = {
    "progressive": {"PROGRESSIVE", "CENTRIST"},
    "moderate": {"PROGRESSIVE", "CENTRIST", "CONSERVATIVE"},
    "centrist": {"CENTRIST", "PROGRESSIVE", "CONSERVATIVE"},
    "conservative": {"CONSERVATIVE", "CENTRIST"},
}

# 선호 스펙트럼의 "반대" 편 라벨 (opposing view 추천에 사용)
_SPECTRUM_OPPOSITE: dict[str, set[str]] = {
    "progressive": {"CONSERVATIVE", "FAR_RIGHT"},
    "moderate": {"PROGRESSIVE", "CONSERVATIVE"},
    "centrist": {"PROGRESSIVE", "CONSERVATIVE"},
    "conservative": {"PROGRESSIVE", "FAR_LEFT"},
}


# ─────────────────────────────────────────────────────────────
# 조회 / 생성
# ─────────────────────────────────────────────────────────────
async def get_or_create_calibration(user_id: str) -> dict[str, Any]:
    """사용자 캘리브레이션을 조회. 없으면 ``DEFAULT_CALIBRATION`` 으로 생성."""
    if not user_id:
        return copy.deepcopy(DEFAULT_CALIBRATION) | {"userId": None}

    try:
        row = await prisma.userbiascalibration.find_unique(where={"userId": user_id})
    except Exception as exc:  # noqa: BLE001
        logger.debug("calibration find failed: %s", exc)
        row = None

    if row:
        return _row_to_dict(row)

    # 생성
    data = copy.deepcopy(DEFAULT_CALIBRATION)
    data["userId"] = user_id
    try:
        row = await prisma.userbiascalibration.create(data=data)
        return _row_to_dict(row)
    except Exception as exc:  # noqa: BLE001
        logger.warning("calibration create failed: %s", exc)
        return data


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "userId": getattr(row, "userId", None),
        "preferredSpectrum": getattr(row, "preferredSpectrum", "centrist"),
        "toleranceRange": float(getattr(row, "toleranceRange", 0.3) or 0.3),
        "showOpposing": bool(getattr(row, "showOpposing", True)),
        "guardrailMode": getattr(row, "guardrailMode", "balanced"),
        "preferences": dict(getattr(row, "preferences", {}) or {}),
    }


# ─────────────────────────────────────────────────────────────
# 업데이트 (가드레일 포함)
# ─────────────────────────────────────────────────────────────
async def update_calibration(
    user_id: str,
    *,
    admin: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    """사용자 캘리브레이션을 안전하게 업데이트.

    적용 규칙:
      - ``toleranceRange`` 는 [0, 0.6] 으로 클램프 (극단 방지).
      - ``preferredSpectrum`` / ``guardrailMode`` 는 허용 값 검증.
      - ``guardrailMode="off"`` 는 ``admin=True`` 일 때만 적용. 일반 사용자가
        요청하면 ``"balanced"`` 로 강등된다.
      - 급격한 변화(:func:`is_extreme_change`) 는 쓰기는 하되 경고를 함께 반환.
    """
    current = await get_or_create_calibration(user_id)
    allowed = {"preferredSpectrum", "toleranceRange", "showOpposing", "guardrailMode", "preferences"}
    updates: dict[str, Any] = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    warnings: list[str] = []

    # preferredSpectrum 검증
    if "preferredSpectrum" in updates:
        if updates["preferredSpectrum"] not in _VALID_SPECTRUMS:
            warnings.append(
                f"preferredSpectrum={updates['preferredSpectrum']!r} 무효 → 무시"
            )
            updates.pop("preferredSpectrum")

    # toleranceRange 클램프
    if "toleranceRange" in updates:
        try:
            tr = float(updates["toleranceRange"])
        except (TypeError, ValueError):
            warnings.append("toleranceRange 숫자 아님 → 무시")
            updates.pop("toleranceRange")
        else:
            clamped = max(0.0, min(_MAX_USER_TOLERANCE, tr))
            if clamped != tr:
                warnings.append(
                    f"toleranceRange {tr} → {clamped} 로 클램프 (극단 방지 상한 {_MAX_USER_TOLERANCE})"
                )
            updates["toleranceRange"] = clamped

    # guardrailMode 검증 + off 는 admin 전용
    if "guardrailMode" in updates:
        mode = updates["guardrailMode"]
        if mode not in _VALID_GUARDRAILS:
            warnings.append(f"guardrailMode={mode!r} 무효 → 무시")
            updates.pop("guardrailMode")
        elif mode == "off" and not admin:
            warnings.append("guardrailMode=off 는 관리자만 가능 → balanced 로 강등")
            updates["guardrailMode"] = "balanced"

    # 급격한 변화 경고
    if is_extreme_change(current, updates):
        warnings.append("설정이 급변했습니다. 점진적 변경을 권장합니다.")

    if not updates:
        return {**current, "warnings": warnings}

    try:
        row = await prisma.userbiascalibration.update(
            where={"userId": user_id}, data=updates
        )
        return {**_row_to_dict(row), "warnings": warnings}
    except Exception as exc:  # noqa: BLE001
        logger.warning("calibration update failed: %s", exc)
        return {**current, **updates, "warnings": warnings + [f"db_error: {exc}"]}


# ─────────────────────────────────────────────────────────────
# 선호 호환성 체크
# ─────────────────────────────────────────────────────────────
def is_within_preference(user_pref: str, fact_bias_label: str) -> bool:
    """선호 스펙트럼이 사실의 ``biasLabel`` 과 호환되는지.

    - ``user_pref`` 는 progressive/moderate/centrist/conservative.
    - 사실이 비정치(``NON_POLITICAL``, ``UNKNOWN``, ``MIXED``) 면 언제나 호환.
    """
    if fact_bias_label in {"NON_POLITICAL", "UNKNOWN", "MIXED", None, ""}:
        return True
    allowed = _SPECTRUM_TO_LABELS.get(user_pref, {"CENTRIST"})
    return fact_bias_label in allowed


def is_extreme_change(current: dict[str, Any], updates: dict[str, Any]) -> bool:
    """급격한 변화 감지.

    기준:
      - ``toleranceRange`` 가 0.25 이상 증가
      - ``preferredSpectrum`` 이 양 끝으로 점프 (progressive ↔ conservative)
      - ``guardrailMode`` 가 strict → off 로 직행
    """
    # toleranceRange 점프
    cur_tr = float(current.get("toleranceRange") or 0.3)
    new_tr = updates.get("toleranceRange")
    if new_tr is not None:
        try:
            if float(new_tr) - cur_tr >= 0.25:
                return True
        except (TypeError, ValueError):
            pass

    # spectrum 점프
    cur_sp = current.get("preferredSpectrum") or "centrist"
    new_sp = updates.get("preferredSpectrum")
    if new_sp and {cur_sp, new_sp} == {"progressive", "conservative"}:
        return True

    # guardrail 완화
    cur_g = current.get("guardrailMode") or "balanced"
    new_g = updates.get("guardrailMode")
    if new_g and cur_g == "strict" and new_g == "off":
        return True

    return False


# ─────────────────────────────────────────────────────────────
# 사실 필터링 (가드레일 + 반대관점 보강)
# ─────────────────────────────────────────────────────────────
async def filter_facts_for_user(
    user_id: str, facts: list[KnowledgeFact]
) -> dict[str, Any]:
    """사용자 캘리브레이션에 따라 사실 목록을 필터링.

    절차:
      1. ``guardrailMode`` 의 ``block_extreme`` / ``excluded_labels`` 적용.
      2. ``showOpposing=False`` 면 선호 스펙트럼과 호환되는 사실만 유지.
      3. ``balanced`` / ``strict`` 모드에서는 반대 관점이 ``min_opposing_ratio``
         비만큼 있는지 검사하고, 모자라면 :func:`find_stance_diverse_facts` 로
         보강 시도.

    반환::

        {
          "displayed": [...],
          "excluded": [...],
          "reasons": {fact_id: reason},
          "balanced_by_guardrail": bool,
        }
    """
    calib = await get_or_create_calibration(user_id)
    policy = GUARDRAIL_POLICIES.get(calib["guardrailMode"], GUARDRAIL_POLICIES["balanced"])
    excluded_labels = set(policy.get("excluded_labels", []))
    block_extreme = bool(policy.get("block_extreme", False))
    min_opp_ratio = float(policy.get("min_opposing_ratio", 0.0))
    show_opposing = bool(calib.get("showOpposing", True))
    spectrum = calib.get("preferredSpectrum", "centrist")

    displayed: list[KnowledgeFact] = []
    excluded: list[KnowledgeFact] = []
    reasons: dict[str, str] = {}

    allowed_labels = _SPECTRUM_TO_LABELS.get(spectrum, {"CENTRIST"})
    opposite_labels = _SPECTRUM_OPPOSITE.get(spectrum, set())

    for f in facts:
        label = _get_bias_label(f)

        # (1) guardrail: 극단 라벨 차단
        if block_extreme and label in excluded_labels:
            excluded.append(f)
            reasons[f.id or ""] = f"guardrail_block_extreme:{label}"
            continue

        # (2) showOpposing=False → 선호에 맞지 않으면 제외 (비정치는 통과)
        if not show_opposing and not is_within_preference(spectrum, label):
            excluded.append(f)
            reasons[f.id or ""] = f"outside_preference:{label}"
            continue

        displayed.append(f)

    # (3) 반대 관점 최소 비율 보장 (balanced / strict)
    balanced_by_guardrail = False
    if min_opp_ratio > 0.0 and displayed:
        opp_count = sum(1 for f in displayed if _get_bias_label(f) in opposite_labels)
        total = len(displayed)
        ratio = opp_count / max(1, total)
        if ratio < min_opp_ratio:
            # 반대 관점 보강 시도
            entities = {f.entity for f in displayed if f.entity}
            added = 0
            need = max(1, int(min_opp_ratio * total) - opp_count)
            for entity in list(entities)[:3]:
                try:
                    diverse = await find_stance_diverse_facts(entity)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("find_stance_diverse_facts failed: %s", exc)
                    diverse = {}
                # contested / opinion / interpretation 순으로 보강
                for bucket_key in ("contested", "opinion", "interpretation", "factual"):
                    for item in diverse.get(bucket_key, [])[:3]:
                        item_label = item.get("bias_label") or "UNKNOWN"
                        if item_label not in opposite_labels:
                            continue
                        # 중복 방지
                        if any(f.id == item.get("id") for f in displayed):
                            continue
                        # 모든 필드를 채운 완전한 KnowledgeFact 로는 재구성이 어렵다.
                        # 보강용 간이 인스턴스는 필수 필드만 채워 사용.
                        try:
                            supplement = KnowledgeFact(
                                id=item.get("id"),
                                content=item.get("content", ""),
                                source=item.get("source", ""),
                                domain=item.get("domain", "general"),
                                entity=item.get("entity"),
                                valid_from=datetime.now(timezone.utc),
                            )
                            displayed.append(supplement)
                            added += 1
                            balanced_by_guardrail = True
                            reasons[supplement.id or f"suppl_{added}"] = (
                                "guardrail_supplement_opposing"
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.debug("supplement fact build failed: %s", exc)
                        if added >= need:
                            break
                    if added >= need:
                        break
                if added >= need:
                    break

    return {
        "displayed": displayed,
        "excluded": excluded,
        "reasons": reasons,
        "balanced_by_guardrail": balanced_by_guardrail,
        "applied_policy": calib["guardrailMode"],
        "preferred_spectrum": spectrum,
    }


def _get_bias_label(f: KnowledgeFact | Any) -> str:
    """KnowledgeFact / row / dict 등 어느 쪽에서든 biasLabel 을 꺼낸다."""
    if f is None:
        return "UNKNOWN"
    if isinstance(f, dict):
        return str(f.get("biasLabel") or f.get("bias_label") or "UNKNOWN")
    label = getattr(f, "biasLabel", None) or getattr(f, "bias_label", None)
    if label:
        return str(label)
    # 점수만 있으면 역산
    score = getattr(f, "biasScore", None) or getattr(f, "bias_score", None)
    if score is not None:
        try:
            return score_to_label(float(score))
        except Exception:  # noqa: BLE001
            pass
    return "UNKNOWN"


# ─────────────────────────────────────────────────────────────
# 사용자 편향 프로파일 (히스토리 기반)
# ─────────────────────────────────────────────────────────────
async def compute_user_bias_profile_from_history(
    user_id: str, recent_days: int = 30
) -> dict[str, Any]:
    """사용자의 최근 긍정 피드백 기록을 바탕으로 **실제 선호 성향** 을 진단.

    즉, "본인이 설정한 선호" 와 "실제 행동에서 드러난 선호" 를 비교할 수 있게
    한다. (설정은 중도라지만 실제로는 보수 사실에만 좋아요를 누를 수도.)
    """
    if not user_id:
        return {"userId": None, "dominant": "UNKNOWN", "distribution": {}, "samples": 0}

    since = datetime.now(timezone.utc) - timedelta(days=max(1, recent_days))
    label_counts: dict[str, int] = {}
    samples = 0

    # KnowledgeFeedback 테이블을 가정. 없으면 빈 결과.
    try:
        feedbacks = await prisma.knowledgefeedback.find_many(
            where={
                "userId": user_id,
                "feedback": {"in": ["POSITIVE", "LIKE", "HELPFUL"]},
                "createdAt": {"gte": since},
            },
            take=500,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("feedback lookup failed: %s", exc)
        feedbacks = []

    fact_ids = [getattr(fb, "factId", None) for fb in feedbacks if getattr(fb, "factId", None)]
    if fact_ids:
        try:
            rows = await prisma.knowledgefact.find_many(where={"id": {"in": fact_ids}})
        except Exception:
            rows = []
        for r in rows:
            label = getattr(r, "biasLabel", None) or "UNKNOWN"
            label_counts[label] = label_counts.get(label, 0) + 1
            samples += 1

    dominant = "UNKNOWN"
    if label_counts:
        dominant = max(label_counts.items(), key=lambda kv: kv[1])[0]

    diagnosis = ""
    if samples >= 5 and dominant not in {"UNKNOWN", "NON_POLITICAL"}:
        diagnosis = f"최근 {recent_days}일간 긍정 피드백의 다수(={dominant})가 특정 성향에 쏠려 있습니다."

    return {
        "userId": user_id,
        "dominant": dominant,
        "distribution": label_counts,
        "samples": samples,
        "recent_days": recent_days,
        "diagnosis": diagnosis,
    }


# ─────────────────────────────────────────────────────────────
# 필터 버블 경고
# ─────────────────────────────────────────────────────────────
async def warn_if_filter_bubble(
    user_id: str, threshold: float = 0.7
) -> dict[str, Any] | None:
    """최근 피드백이 한쪽 라벨로 ``threshold`` 이상 쏠려 있으면 경고.

    반환 없음(None) = 경고 없음. dict 반환 시 UI 에서 배너로 노출 권장.
    """
    profile = await compute_user_bias_profile_from_history(user_id, recent_days=30)
    dist = profile.get("distribution", {})
    samples = profile.get("samples", 0)
    if samples < 5 or not dist:
        return None

    total = sum(dist.values()) or 1
    dominant, count = max(dist.items(), key=lambda kv: kv[1])
    ratio = count / total
    if ratio < threshold:
        return None
    if dominant in {"UNKNOWN", "NON_POLITICAL", "MIXED"}:
        return None

    return {
        "warning": True,
        "dominant_label": dominant,
        "ratio": round(ratio, 3),
        "samples": samples,
        "message": (
            f"최근 피드백의 {ratio*100:.0f}% 가 {dominant} 성향입니다. "
            "편향 버블에 갇혀 있을 수 있어요. 반대 관점 보기 권장."
        ),
    }


# ─────────────────────────────────────────────────────────────
# 반대 관점 추천
# ─────────────────────────────────────────────────────────────
async def suggest_opposing_view(
    user_id: str, entity: str, limit: int = 5
) -> list[dict[str, Any]]:
    """사용자 스펙트럼의 **반대편** 에서 같은 entity 관련 사실을 추천.

    stance_diverse_facts 중 biasLabel 이 반대편에 해당하는 항목을 우선 반환.
    """
    if not entity:
        return []

    calib = await get_or_create_calibration(user_id)
    spectrum = calib.get("preferredSpectrum", "centrist")
    opposite = _SPECTRUM_OPPOSITE.get(spectrum, set())

    try:
        diverse = await find_stance_diverse_facts(entity)
    except Exception as exc:  # noqa: BLE001
        logger.debug("find_stance_diverse_facts failed: %s", exc)
        diverse = {}

    picks: list[dict[str, Any]] = []
    for bucket in ("contested", "interpretation", "opinion", "factual"):
        for item in diverse.get(bucket, []):
            label = item.get("bias_label") or "UNKNOWN"
            if label in opposite:
                picks.append(item)
                if len(picks) >= limit:
                    return picks

    # 반대편 라벨이 부족하면 entity 기반 일반 검색으로 보강
    if len(picks) < limit:
        try:
            rows = await prisma.knowledgefact.find_many(
                where={"entity": entity, "biasLabel": {"in": list(opposite)}},
                take=limit,
            )
            for r in rows:
                picks.append(
                    {
                        "id": r.id,
                        "content": getattr(r, "content", "")[:200],
                        "source": getattr(r, "source", ""),
                        "bias_label": getattr(r, "biasLabel", "UNKNOWN"),
                    }
                )
                if len(picks) >= limit:
                    break
        except Exception as exc:  # noqa: BLE001
            logger.debug("suggest_opposing_view fallback failed: %s", exc)

    return picks[:limit]


# ─────────────────────────────────────────────────────────────
# 관리자 도구
# ─────────────────────────────────────────────────────────────
async def enforce_guardrail_globally(enabled: bool, admin_user_id: str) -> None:
    """관리자가 전체 시스템에 guardrail 최소치를 강제/해제.

    enabled=True  → 모든 사용자의 ``guardrailMode`` 가 ``off`` 면 ``balanced`` 로 승격.
    enabled=False → 정책 변경 기록만 남기고 개인 설정은 건드리지 않는다.
    """
    if not admin_user_id:
        raise PermissionError("admin_user_id required")

    if enabled:
        try:
            await prisma.userbiascalibration.update_many(
                where={"guardrailMode": "off"},
                data={"guardrailMode": "balanced"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("enforce_guardrail_globally update_many failed: %s", exc)

    # 감사 로그 (AuditLog 테이블이 있으면 기록)
    try:
        await prisma.auditlog.create(
            data={
                "userId": admin_user_id,
                "action": "enforce_guardrail_globally",
                "details": {"enabled": enabled},
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit log skipped: %s", exc)


async def list_user_calibrations(admin_only: bool = True) -> list[dict[str, Any]]:
    """모든 사용자 캘리브레이션 목록 (관리자 전용 기본값).

    ``admin_only=True`` 는 호출부 책임으로 권한 검사를 수행했다는 의미로
    사용된다. False 를 내부에서 별도로 처리하진 않는다.
    """
    try:
        rows = await prisma.userbiascalibration.find_many(take=1000)
    except Exception as exc:  # noqa: BLE001
        logger.debug("list_user_calibrations failed: %s", exc)
        return []
    return [_row_to_dict(r) for r in rows]


__all__ = [
    "DEFAULT_CALIBRATION",
    "GUARDRAIL_POLICIES",
    "get_or_create_calibration",
    "update_calibration",
    "is_within_preference",
    "is_extreme_change",
    "filter_facts_for_user",
    "compute_user_bias_profile_from_history",
    "warn_if_filter_bubble",
    "suggest_opposing_view",
    "enforce_guardrail_globally",
    "list_user_calibrations",
]
