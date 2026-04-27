"""도메인 전문화 설정 (소유자 명시적 선언)

auto_specialization.py 가 "자동 발견"이라면, 이 모듈은 "소유자의 명시적 선언"이다.

원칙:
    - 에이전트는 PARTICIPANT. 마스터가 라운드를 공지하면 내가 맞는지 판단.
    - 소유자 의도가 자동 발견보다 우선 (owner override).
    - 법률/의료/세무 전문가 사용자는 자기 분야 라운드만 받도록 설정 가능.
    - HLKM ExpertCredential과 연결하여 "인증된 전문가" 가중치 부여.

파일 구조:
    ~/.hwarang/agent_profile.yaml  (없으면 JSON fallback)

프리셋 예시:
    general              - 범용 (모든 도메인)
    law_specialist       - 법률 전문
    medical_specialist   - 의료 전문
    tax_specialist       - 세무 전문
    legal_and_tax        - 법률+세무 복합 (세무사+변호사)
    night_only           - 야간 전용 (22:00~07:00)

HWARANG_EXPERT_WEIGHT:
    HLKM 자격증 타입별 라운드 참여 가중치.
    인증된 전문가일수록 해당 도메인 라운드에서 선발 확률↑ + 보상↑.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

try:  # PyYAML optional
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

try:  # httpx optional
    import httpx  # type: ignore
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# 상수 / 테이블
# ----------------------------------------------------------------------------

DOMAIN_PRIORITY_MAP: dict[str, list[str]] = {
    "law": ["law", "law:criminal", "law:civil", "law:labor", "law:tax"],
    "medical": [
        "medical",
        "medical:cardiology",
        "medical:oncology",
        "medical:psychiatry",
        "medical:pediatrics",
    ],
    "tax": ["tax", "tax:corporate", "tax:personal", "tax:vat", "law:tax"],
}

# HLKM ExpertCredential 타입 → 라운드 참여 가중치 (1.0 = 중립)
HWARANG_EXPERT_WEIGHT: dict[str, float] = {
    # 법률
    "BAR_KR":                1.80,  # 대한변호사협회 등록
    "JUDICIAL_SCRIVENER_KR": 1.35,  # 법무사
    "PATENT_ATTORNEY_KR":    1.40,  # 변리사
    # 의료
    "MD_KR":                 1.80,  # 의사면허
    "SPECIALIST_KR":         1.95,  # 전문의
    "PHARMACIST_KR":         1.45,  # 약사
    "NURSE_KR":              1.25,  # 간호사
    # 세무/회계
    "CTA_KR":                1.80,  # 세무사
    "CPA_KR":                1.75,  # 공인회계사
    # 학계/연구
    "PHD_DOMAIN":            1.50,  # 해당 도메인 박사
    "POSTDOC":               1.30,  # 박사후 연구원
    # 일반
    "GENERAL_USER":          1.00,
}

# 데이터 품질 티어 (HLKM)
DATA_QUALITY_TIERS: list[str] = [
    "PRIMARY_OFFICIAL",    # 법령 원문/판례 원본
    "PEER_REVIEWED",       # 학술 논문
    "SPECIALIZED_MEDIA",   # 전문 매체
    "GENERAL_MEDIA",       # 일반 매체
    "USER_GENERATED",      # 블로그/커뮤니티
]

SUPPORTED_PRESETS: dict[str, dict[str, Any]] = {
    "general": {
        "primary": [],
        "excluded": [],
        "level": "general",
        "description": "범용 (모든 도메인 라운드 수신)",
    },
    "law_specialist": {
        "primary": ["law"],
        "excluded": ["medical", "politics"],
        "level": "expert",
        "description": "법률 전문 (변호사/법무사)",
    },
    "medical_specialist": {
        "primary": ["medical"],
        "excluded": ["law", "politics"],
        "level": "expert",
        "description": "의료 전문 (의사/약사)",
    },
    "tax_specialist": {
        "primary": ["tax", "law:tax", "finance"],
        "excluded": ["medical", "politics"],
        "level": "expert",
        "description": "세무 전문 (세무사/회계사)",
    },
    "legal_and_tax": {
        "primary": ["law", "tax"],
        "excluded": ["medical", "politics"],
        "level": "expert",
        "description": "법률+세무 복합 (변호사이면서 세무 겸업)",
    },
    "night_only": {
        "primary": [],
        "excluded": [],
        "level": "general",
        "active_hours": "22:00-07:00",
        "description": "야간 전용 (전기세 심야 할인 시간대)",
    },
}

DEFAULT_PATH = "~/.hwarang/agent_profile.yaml"


# ----------------------------------------------------------------------------
# Dataclass
# ----------------------------------------------------------------------------


@dataclass
class DomainProfile:
    """에이전트 소유자의 명시적 도메인 선언."""

    primary_domains: list[str] = field(default_factory=list)
    excluded_domains: list[str] = field(default_factory=list)
    expertise_level: Literal["general", "specialist", "expert"] = "general"
    # HLKM credential id 목록 (e.g. ["BAR_KR:12345", "CTA_KR:67890"])
    owner_expert_credentials: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=lambda: ["ko"])
    # 최소 허용 데이터 품질 (이보다 낮으면 라운드 거부)
    min_data_quality_tier: str = "GENERAL_MEDIA"
    # "HH:MM-HH:MM" (자정 통과 허용) 또는 None = 24시간
    active_hours: str | None = None
    max_concurrent_rounds: int = 1
    auto_participate: bool = True
    preset: str = "general"
    owner_user_id: str | None = None


# ----------------------------------------------------------------------------
# Load / Save
# ----------------------------------------------------------------------------


def _resolve_path(path: str) -> Path:
    return Path(os.path.expanduser(path))


def load_profile(path: str = DEFAULT_PATH) -> DomainProfile:
    """프로필 로드.

    YAML 우선, 없으면 JSON fallback (같은 경로의 .json),
    그것도 없으면 기본 DomainProfile 반환.
    """
    p = _resolve_path(path)

    # 1. YAML
    if p.exists() and yaml is not None:
        try:
            with p.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return _from_dict(data)
        except Exception as e:
            logger.warning("YAML 로드 실패, JSON fallback 시도: %s", e)

    # 2. JSON fallback
    json_path = p.with_suffix(".json")
    if json_path.exists():
        try:
            with json_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return _from_dict(data)
        except Exception as e:
            logger.warning("JSON 로드 실패: %s", e)

    # 3. 기본
    logger.info("프로필 파일 없음 → 기본 general 프로필 사용")
    return DomainProfile()


def save_profile(profile: DomainProfile, path: str = DEFAULT_PATH) -> None:
    """프로필 저장. YAML 가능하면 YAML, 아니면 JSON."""
    p = _resolve_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    data = asdict(profile)

    if yaml is not None:
        with p.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
        logger.info("프로필 저장 (YAML): %s", p)
    else:
        json_path = p.with_suffix(".json")
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("프로필 저장 (JSON): %s", json_path)


def _from_dict(data: dict[str, Any]) -> DomainProfile:
    """dict → DomainProfile (누락 필드는 기본값)."""
    known = {k: v for k, v in data.items() if k in DomainProfile.__dataclass_fields__}
    return DomainProfile(**known)


# ----------------------------------------------------------------------------
# Presets
# ----------------------------------------------------------------------------


def apply_preset(
    preset_name: str,
    existing_profile: DomainProfile | None = None,
    merge: bool = False,
) -> DomainProfile:
    """프리셋 적용.

    Args:
        preset_name: SUPPORTED_PRESETS의 키
        existing_profile: 기존 프로필 (merge=True일 때 보존)
        merge: True면 기존 owner_expert_credentials/languages 유지
    """
    if preset_name not in SUPPORTED_PRESETS:
        raise ValueError(
            f"알 수 없는 프리셋: {preset_name}. "
            f"사용 가능: {list(SUPPORTED_PRESETS.keys())}"
        )

    spec = SUPPORTED_PRESETS[preset_name]
    new = DomainProfile(
        primary_domains=list(spec.get("primary", [])),
        excluded_domains=list(spec.get("excluded", [])),
        expertise_level=spec.get("level", "general"),
        active_hours=spec.get("active_hours"),
        preset=preset_name,
    )

    if merge and existing_profile is not None:
        new.owner_expert_credentials = list(existing_profile.owner_expert_credentials)
        new.languages = list(existing_profile.languages)
        new.owner_user_id = existing_profile.owner_user_id
        new.max_concurrent_rounds = existing_profile.max_concurrent_rounds
        new.auto_participate = existing_profile.auto_participate
        new.min_data_quality_tier = existing_profile.min_data_quality_tier

    logger.info("프리셋 적용: %s (merge=%s)", preset_name, merge)
    return new


def list_presets() -> list[dict[str, Any]]:
    """사용 가능한 프리셋 목록 + 설명."""
    out: list[dict[str, Any]] = []
    for name, spec in SUPPORTED_PRESETS.items():
        out.append({
            "name": name,
            "description": spec.get("description", ""),
            "primary_domains": list(spec.get("primary", [])),
            "excluded_domains": list(spec.get("excluded", [])),
            "expertise_level": spec.get("level", "general"),
            "active_hours": spec.get("active_hours"),
        })
    return out


# ----------------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------------


def validate_profile(profile: DomainProfile) -> list[str]:
    """유효성 검사. 오류/경고 메시지 목록 반환 (빈 리스트 = OK)."""
    errors: list[str] = []

    # 겹침 검사
    overlap = set(profile.primary_domains) & set(profile.excluded_domains)
    if overlap:
        errors.append(
            f"primary와 excluded가 겹침: {sorted(overlap)}"
        )

    # expert 레벨인데 자격증 없음 → 경고
    if profile.expertise_level == "expert" and not profile.owner_expert_credentials:
        errors.append(
            "expertise_level=expert 인데 owner_expert_credentials 비어있음 "
            "(HLKM 인증 필요 — 보상 가중치 적용 안됨)"
        )

    # 데이터 티어 검증
    if profile.min_data_quality_tier not in DATA_QUALITY_TIERS:
        errors.append(
            f"min_data_quality_tier '{profile.min_data_quality_tier}' 는 유효하지 않음. "
            f"사용 가능: {DATA_QUALITY_TIERS}"
        )

    # active_hours 포맷
    if profile.active_hours:
        try:
            _parse_active_hours(profile.active_hours)
        except ValueError as e:
            errors.append(f"active_hours 포맷 오류: {e}")

    # 동시 실행 수
    if profile.max_concurrent_rounds < 1:
        errors.append("max_concurrent_rounds >= 1 이어야 함")

    return errors


# ----------------------------------------------------------------------------
# 시간대 체크
# ----------------------------------------------------------------------------


def _parse_active_hours(spec: str) -> tuple[int, int, int, int]:
    """'22:00-07:00' → (22, 0, 7, 0)."""
    try:
        start_s, end_s = spec.split("-")
        sh, sm = map(int, start_s.strip().split(":"))
        eh, em = map(int, end_s.strip().split(":"))
        if not (0 <= sh < 24 and 0 <= eh < 24 and 0 <= sm < 60 and 0 <= em < 60):
            raise ValueError("시/분 범위 초과")
        return sh, sm, eh, em
    except Exception as e:
        raise ValueError(f"'HH:MM-HH:MM' 형식이어야 함: {spec} ({e})")


def is_active_now(profile: DomainProfile, now: datetime | None = None) -> bool:
    """active_hours 체크. None이면 항상 True (24시간)."""
    if not profile.active_hours:
        return True
    now = now or datetime.now()
    try:
        sh, sm, eh, em = _parse_active_hours(profile.active_hours)
    except ValueError:
        return True

    cur = now.hour * 60 + now.minute
    start = sh * 60 + sm
    end = eh * 60 + em

    if start <= end:
        return start <= cur < end
    # 자정 통과 (22:00-07:00)
    return cur >= start or cur < end


# ----------------------------------------------------------------------------
# 라운드 매칭
# ----------------------------------------------------------------------------


def _credential_boost(profile: DomainProfile, domain: str) -> float:
    """HLKM 자격증에 따른 가중치 계산."""
    if not profile.owner_expert_credentials:
        return 1.0

    best = 1.0
    dom_root = domain.split(":")[0]
    law_like = {"law", "tax"}  # 겹치는 영역
    for cred in profile.owner_expert_credentials:
        cred_type = cred.split(":")[0].strip().upper()
        weight = HWARANG_EXPERT_WEIGHT.get(cred_type, 1.0)

        # 도메인과 자격증 궁합
        matched = False
        if dom_root == "law" and cred_type in {"BAR_KR", "JUDICIAL_SCRIVENER_KR", "PATENT_ATTORNEY_KR"}:
            matched = True
        elif dom_root == "medical" and cred_type in {"MD_KR", "SPECIALIST_KR", "PHARMACIST_KR", "NURSE_KR"}:
            matched = True
        elif dom_root == "tax" and cred_type in {"CTA_KR", "CPA_KR"}:
            matched = True
        elif cred_type == "PHD_DOMAIN" or cred_type == "POSTDOC":
            matched = True  # 도메인 무관하게 연구 신뢰도 보너스 (일부)

        if matched and weight > best:
            best = weight
    _ = law_like  # silence unused
    return best


def _tier_index(tier: str) -> int:
    try:
        return DATA_QUALITY_TIERS.index(tier)
    except ValueError:
        return len(DATA_QUALITY_TIERS)  # 알수없음 = 최하


def match_round_to_profile(round_meta: dict, profile: DomainProfile) -> dict:
    """라운드가 내 프로필과 얼마나 맞는지 점수화.

    Args:
        round_meta: {"domain": "law", "min_tier_required": "SILVER",
                     "data_tier": "PEER_REVIEWED", "language": "ko", ...}
        profile: 내 DomainProfile

    Returns:
        {"match_score": 0.0~1.0, "reasons": [...], "is_eligible": bool,
         "credential_boost": 1.0~2.0}
    """
    reasons: list[str] = []
    domain = round_meta.get("domain", "")
    domain_root = domain.split(":")[0] if domain else ""

    # 1. 제외 도메인
    for ex in profile.excluded_domains:
        if domain == ex or domain_root == ex or domain.startswith(ex + ":"):
            return {
                "match_score": 0.0,
                "reasons": [f"제외 도메인 매치: {ex}"],
                "is_eligible": False,
                "credential_boost": 1.0,
            }

    # 2. 시간대
    if not is_active_now(profile):
        return {
            "match_score": 0.0,
            "reasons": [f"비활성 시간대 (active_hours={profile.active_hours})"],
            "is_eligible": False,
            "credential_boost": 1.0,
        }

    # 3. 언어
    round_lang = round_meta.get("language", "ko")
    if round_lang not in profile.languages:
        reasons.append(f"언어 불일치 (라운드={round_lang}, 내={profile.languages})")
        return {
            "match_score": 0.1,
            "reasons": reasons,
            "is_eligible": False,
            "credential_boost": 1.0,
        }

    # 4. 데이터 품질 티어
    round_tier = round_meta.get("data_tier", "GENERAL_MEDIA")
    if _tier_index(round_tier) > _tier_index(profile.min_data_quality_tier):
        reasons.append(
            f"데이터 품질 미달 (라운드={round_tier}, 최소={profile.min_data_quality_tier})"
        )
        return {
            "match_score": 0.2,
            "reasons": reasons,
            "is_eligible": False,
            "credential_boost": 1.0,
        }

    # 5. 기본 점수
    score = 0.5

    # 6. primary 매치
    if profile.primary_domains:
        matched = False
        for pd in profile.primary_domains:
            if domain == pd or domain_root == pd or domain.startswith(pd + ":"):
                matched = True
                reasons.append(f"주력 도메인 매치: {pd}")
                score = 0.95
                break
        if not matched:
            # primary 지정돼 있는데 맞는 게 없으면 낮은 점수
            score = 0.3
            reasons.append("주력 도메인 비매치 (보조 참여 가능)")
    else:
        # primary 없음 = 범용 에이전트
        score = 0.7
        reasons.append("범용 에이전트 — 중립 점수")

    # 7. 자격증 부스트
    boost = _credential_boost(profile, domain)
    if boost > 1.0:
        reasons.append(f"HLKM 자격증 부스트 x{boost:.2f}")

    final_score = min(1.0, score * (boost ** 0.5))  # 부스트는 제곱근 적용 (과도함 방지)

    return {
        "match_score": round(final_score, 3),
        "reasons": reasons,
        "is_eligible": True,
        "credential_boost": round(boost, 2),
    }


# ----------------------------------------------------------------------------
# 마스터 동기화
# ----------------------------------------------------------------------------


async def sync_with_master(
    master_url: str,
    agent_id: str,
    profile: DomainProfile,
    api_key: str,
    timeout: float = 10.0,
) -> bool:
    """프로필을 마스터에 업로드 (라운드 매칭에 사용).

    POST /api/grid/agents/{agent_id}/profile
    """
    if httpx is None:
        logger.warning("httpx 미설치 — sync_with_master 스킵")
        return False

    url = f"{master_url.rstrip('/')}/api/grid/agents/{agent_id}/profile"
    payload = asdict(profile)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            logger.info("프로필 마스터 동기화 완료: agent_id=%s", agent_id)
            return True
    except Exception as e:
        logger.error("마스터 동기화 실패: %s", e)
        return False


# ----------------------------------------------------------------------------
# CLI 테스트
# ----------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")

    print("=== 프리셋 목록 ===")
    for p in list_presets():
        print(f"  {p['name']:20s} — {p['description']}")

    print("\n=== law_specialist 프리셋 적용 ===")
    prof = apply_preset("law_specialist")
    prof.owner_expert_credentials = ["BAR_KR:12345"]
    prof.languages = ["ko", "en"]
    errs = validate_profile(prof)
    print(f"  유효성: {'OK' if not errs else errs}")

    print("\n=== 라운드 매칭 테스트 ===")
    for round_meta in [
        {"domain": "law:criminal", "data_tier": "PEER_REVIEWED", "language": "ko"},
        {"domain": "medical", "data_tier": "PEER_REVIEWED", "language": "ko"},
        {"domain": "law:tax", "data_tier": "PRIMARY_OFFICIAL", "language": "ko"},
    ]:
        r = match_round_to_profile(round_meta, prof)
        print(f"  {round_meta['domain']:20s} → score={r['match_score']:.2f}, "
              f"eligible={r['is_eligible']}, reasons={r['reasons']}")
