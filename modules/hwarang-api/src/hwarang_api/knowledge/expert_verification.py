"""HLKM — 전문가 자격 증명 (Expert Verification).

의사/변호사/교수/회계사 등 전문가의 자격을 제출·검증하고,
해당 도메인에서 기여 가중치(weightMultiplier)를 부여한다.

검증 방법:
  1) document_upload: 자격증 스캔본 업로드 + OCR + 관리자 수동 검증
  2) third_party_api: 대한변호사협회/보건복지부 등 외부 API 조회
  3) admin_review: 관리자가 직접 최종 승인

가중치 적용 규칙:
  - 해당 전문 분야(field) 도메인의 Fact 기여/검토 시 weightMultiplier 배 가산
  - 전문 분야 외 도메인에서는 1.0 (일반인과 동일)

의존:
  - `hwarang_api.db.prisma`
  - `.types.KnowledgeFact`
"""

from __future__ import annotations

import io
import logging
import re
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Optional

import httpx

from hwarang_api.db import prisma

from .types import KnowledgeFact  # noqa: F401 (spec 요구)

logger = logging.getLogger(__name__)


# OCR 의존: 없으면 graceful fallback (관리자 수동 검토)
try:
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
    OCR_AVAILABLE = True
except ImportError:  # pragma: no cover
    pytesseract = None  # type: ignore
    Image = None  # type: ignore
    OCR_AVAILABLE = False


# 자격증 도메인별 자격번호 정규식
_CREDENTIAL_PATTERNS: dict[str, str] = {
    "lawyer": r"제?\s*(\d{4,6})\s*호",            # 변호사 등록 제 12345호
    "doctor": r"의사면허\s*제?\s*(\d{5,6})\s*호",  # 의사 면허 제 123456 호
    "cpa": r"공인회계사\s*제?\s*(\d{4,6})\s*호",
    "tax": r"세무사\s*제?\s*(\d{4,6})\s*호",
    "default": r"제?\s*(\d{4,6})\s*호",
}


async def extract_credential_number(image_bytes: bytes, doc_type: str) -> Optional[str]:
    """자격증 이미지에서 자격번호를 추출.

    doc_type: 'lawyer' (변호사), 'doctor' (의사), 'cpa' (회계사), 'tax' (세무사) 등
    pytesseract / Pillow 미설치 시 None 반환 (관리자 수동 검토 fallback).
    """
    if not OCR_AVAILABLE or not image_bytes:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(img, lang="kor+eng")
    except Exception as e:
        logger.warning("extract_credential_number: OCR failed: %s", e)
        return None

    pattern = _CREDENTIAL_PATTERNS.get(doc_type, _CREDENTIAL_PATTERNS["default"])
    m = re.search(pattern, text)
    return m.group(1) if m else None


# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────
EXPERT_FIELDS: dict[str, list[str]] = {
    "law": ["general", "criminal", "civil", "tax", "labor", "ip"],
    "medical": ["general", "cardiology", "oncology", "pediatrics", "psychiatry"],
    "finance": ["accounting", "tax", "audit"],
    "tech": ["software", "security", "ai_ml"],
    "science": ["physics", "chemistry", "biology"],
}

VERIFICATION_METHODS: list[str] = [
    "document_upload",
    "third_party_api",
    "admin_review",
]

_STATUS_PENDING = "pending"
_STATUS_VERIFIED = "verified"
_STATUS_REJECTED = "rejected"
_STATUS_EXPIRED = "expired"
_STATUS_REVOKED = "revoked"

DEFAULT_WEIGHT_MULTIPLIER = 2.0


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────
def _is_supported_field(field: str) -> bool:
    """field 가 EXPERT_FIELDS 로 지원되는지 확인한다.

    "law" 또는 "law:criminal" 같은 형식 모두 허용.
    """
    if not field:
        return False
    root = field.split(":", 1)[0]
    return root in EXPERT_FIELDS


def _row_to_dict(row) -> dict:
    return {
        "id": row.id,
        "user_id": row.userId,
        "field": row.field,
        "organization": row.organization,
        "license_number": row.licenseNumber,
        "document_url": row.documentUrl,
        "verified_by": row.verifiedBy,
        "verified_at": row.verifiedAt,
        "expires_at": row.expiresAt,
        "status": row.status,
        "weight_multiplier": float(row.weightMultiplier or 1.0),
    }


# ─────────────────────────────────────────────
# 자격 제출 / 승인 / 거부
# ─────────────────────────────────────────────
async def submit_credential(
    user_id: str,
    field: str,
    organization: str | None,
    license_number: str | None,
    document_url: str | None,
    note: str | None = None,
) -> str:
    """자격증명을 제출한다. status=pending 으로 저장.

    Return: credential_id
    """
    if not _is_supported_field(field):
        raise ValueError(f"unsupported field: {field}")

    created = await prisma.expertcredential.create(
        data={
            "userId": user_id,
            "field": field,
            "organization": organization,
            "licenseNumber": license_number,
            "documentUrl": document_url,
            "status": _STATUS_PENDING,
            "weightMultiplier": 1.0,
        }
    )
    logger.info(
        "credential submitted: user=%s field=%s id=%s note=%s",
        user_id, field, created.id, note,
    )
    return created.id


async def verify_credential(
    credential_id: str,
    admin_id: str,
    weight_multiplier: float = DEFAULT_WEIGHT_MULTIPLIER,
    expires_at: datetime | None = None,
) -> dict:
    """자격증명을 승인한다.

    - ExpertCredential.status = verified
    - verifiedBy / verifiedAt 설정
    - ContributorProfile.expertTags 에 field 추가
    """
    cred = await prisma.expertcredential.find_unique(where={"id": credential_id})
    if cred is None:
        raise ValueError(f"credential not found: {credential_id}")

    updated = await prisma.expertcredential.update(
        where={"id": credential_id},
        data={
            "status": _STATUS_VERIFIED,
            "verifiedBy": admin_id,
            "verifiedAt": datetime.now(timezone.utc),
            "expiresAt": expires_at,
            "weightMultiplier": float(weight_multiplier),
        },
    )

    # ContributorProfile.expertTags 업데이트 (중복 방지)
    profile = await prisma.contributorprofile.find_unique(
        where={"userId": cred.userId}
    )
    if profile is not None:
        tags = list(profile.expertTags or [])
        if cred.field not in tags:
            tags.append(cred.field)
            await prisma.contributorprofile.update(
                where={"userId": cred.userId},
                data={"expertTags": tags},
            )

    logger.info(
        "credential verified: id=%s user=%s field=%s by=%s",
        credential_id, cred.userId, cred.field, admin_id,
    )
    return _row_to_dict(updated)


async def reject_credential(
    credential_id: str, admin_id: str, reason: str
) -> None:
    """자격증명 제출을 거부한다."""
    await prisma.expertcredential.update(
        where={"id": credential_id},
        data={
            "status": _STATUS_REJECTED,
            "verifiedBy": admin_id,
            "verifiedAt": datetime.now(timezone.utc),
        },
    )
    logger.info(
        "credential rejected: id=%s by=%s reason=%s",
        credential_id, admin_id, reason,
    )


async def list_pending_credentials(field: str | None = None) -> list[dict]:
    """관리자 검토 대기 목록을 조회한다."""
    where: dict = {"status": _STATUS_PENDING}
    if field:
        where["field"] = field
    rows = await prisma.expertcredential.find_many(
        where=where,
        order={"id": "asc"},
        take=500,
    )
    return [_row_to_dict(r) for r in rows]


# ─────────────────────────────────────────────
# 권한 조회
# ─────────────────────────────────────────────
async def is_expert_in(user_id: str, field: str) -> bool:
    """사용자가 유효한 (verified, 미만료) 자격을 가지고 있는지 확인한다."""
    rows = await prisma.expertcredential.find_many(
        where={"userId": user_id, "status": _STATUS_VERIFIED},
        take=50,
    )
    now = datetime.now(timezone.utc)
    for r in rows:
        if r.expiresAt is not None and r.expiresAt < now:
            continue
        if await field_match(field, r.field):
            return True
    return False


async def field_match(fact_domain: str, credential_field: str) -> bool:
    """Fact 도메인과 자격증 field 가 매칭되는지 판정한다.

    매칭 규칙:
      - 동일: "law" == "law"
      - 루트 동일: "law" ↔ "law:criminal"  (루트끼리 매칭)
      - 세부 일치: "law:criminal" == "law:criminal"
      - 크로스 매칭 (credential 세부, fact 루트): 루트 비교
    """
    if not fact_domain or not credential_field:
        return False
    fact_root = fact_domain.split(":", 1)[0]
    cred_root = credential_field.split(":", 1)[0]
    if fact_root != cred_root:
        return False
    # 루트 일치 시: credential 이 루트만이면 OK,
    # fact 이 세부 지정 시에도 루트 expert 는 허용.
    if ":" not in credential_field:
        return True
    # credential 이 세부 지정: fact 도 동일 세부이거나 루트
    cred_sub = credential_field.split(":", 1)[1]
    if ":" not in fact_domain:
        return True  # fact 루트 → 세부 expert 도 매칭 허용
    fact_sub = fact_domain.split(":", 1)[1]
    return cred_sub == fact_sub


async def get_expert_multiplier(user_id: str, fact_domain: str) -> float:
    """해당 도메인에서 사용자의 expert 가중치 배수를 반환한다.

    - 유효한 credential 이 매칭되면 weightMultiplier
    - 아니면 1.0
    """
    rows = await prisma.expertcredential.find_many(
        where={"userId": user_id, "status": _STATUS_VERIFIED},
        take=50,
    )
    now = datetime.now(timezone.utc)
    best = 1.0
    for r in rows:
        if r.expiresAt is not None and r.expiresAt < now:
            continue
        if await field_match(fact_domain, r.field):
            mult = float(r.weightMultiplier or 1.0)
            if mult > best:
                best = mult
    return best


# ─────────────────────────────────────────────
# 만료 / 취소
# ─────────────────────────────────────────────
async def expire_credentials() -> int:
    """expiresAt 지난 자격을 status=expired 로 전환한다.

    Return: 만료 처리된 건수.
    """
    now = datetime.now(timezone.utc)
    rows = await prisma.expertcredential.find_many(
        where={
            "status": _STATUS_VERIFIED,
            "expiresAt": {"lt": now, "not": None},
        },
        take=1000,
    )
    count = 0
    for r in rows:
        await prisma.expertcredential.update(
            where={"id": r.id},
            data={"status": _STATUS_EXPIRED},
        )
        # ContributorProfile.expertTags 에서도 제거
        profile = await prisma.contributorprofile.find_unique(
            where={"userId": r.userId}
        )
        if profile is not None:
            tags = [t for t in (profile.expertTags or []) if t != r.field]
            if len(tags) != len(profile.expertTags or []):
                await prisma.contributorprofile.update(
                    where={"userId": r.userId},
                    data={"expertTags": tags},
                )
        count += 1
    logger.info("expire_credentials: %d rows", count)
    return count


async def revoke_credential(
    credential_id: str, admin_id: str, reason: str
) -> None:
    """자격증명을 취소한다 (위조 발각 등).

    - status=revoked
    - ContributorProfile.expertTags 에서 제거
    """
    cred = await prisma.expertcredential.find_unique(where={"id": credential_id})
    if cred is None:
        raise ValueError(f"credential not found: {credential_id}")

    await prisma.expertcredential.update(
        where={"id": credential_id},
        data={
            "status": _STATUS_REVOKED,
            "verifiedBy": admin_id,
            "verifiedAt": datetime.now(timezone.utc),
        },
    )

    profile = await prisma.contributorprofile.find_unique(
        where={"userId": cred.userId}
    )
    if profile is not None:
        tags = [t for t in (profile.expertTags or []) if t != cred.field]
        await prisma.contributorprofile.update(
            where={"userId": cred.userId},
            data={"expertTags": tags},
        )

    logger.warning(
        "credential revoked: id=%s user=%s field=%s reason=%s by=%s",
        credential_id, cred.userId, cred.field, reason, admin_id,
    )


# ─────────────────────────────────────────────
# 조회 / 통계
# ─────────────────────────────────────────────
async def list_experts_by_field(field: str) -> list[dict]:
    """해당 field 의 verified 전문가 목록을 반환한다."""
    rows = await prisma.expertcredential.find_many(
        where={"field": field, "status": _STATUS_VERIFIED},
        take=500,
    )
    now = datetime.now(timezone.utc)
    out: list[dict] = []
    for r in rows:
        if r.expiresAt is not None and r.expiresAt < now:
            continue
        out.append(_row_to_dict(r))
    return out


async def stats_by_field() -> dict:
    """각 field 별 등록된 verified expert 수 집계."""
    rows = await prisma.expertcredential.find_many(
        where={"status": _STATUS_VERIFIED},
        take=10000,
    )
    now = datetime.now(timezone.utc)
    result: dict[str, int] = {}
    for r in rows:
        if r.expiresAt is not None and r.expiresAt < now:
            continue
        result[r.field] = result.get(r.field, 0) + 1
    return result


# ─────────────────────────────────────────────
# 외부 검증 (Placeholder)
# ─────────────────────────────────────────────
async def ocr_license_number(
    document_url: str, doc_type: str = "default"
) -> str | None:
    """자격증 이미지에서 OCR 로 자격번호를 추출한다.

    파이프라인:
      1) document_url 다운로드 (http/https)
      2) pytesseract (kor+eng) 로 OCR
      3) 도메인별 정규식으로 번호 매칭

    pytesseract / Pillow 미설치 또는 시스템 tesseract 미설치 시 None.
    실패 시 None → 호출 측은 관리자 수동 검토로 fallback.
    """
    if not document_url:
        return None
    if not OCR_AVAILABLE:
        logger.warning("ocr_license_number: pytesseract/PIL not installed")
        return None
    if shutil.which("tesseract") is None:
        logger.warning("ocr_license_number: tesseract binary not installed")
        return None

    # tesseract 정상 동작 여부 한 번만 확인 (debug 로그 only)
    try:
        _ = subprocess.run(  # noqa: S603
            ["tesseract", "--version"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except Exception as e:  # pragma: no cover
        logger.warning("tesseract probe failed: %s", e)
        return None

    # 1) 이미지 다운로드
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(document_url)
            if resp.status_code != 200:
                logger.warning(
                    "ocr_license_number: download failed status=%s url=%s",
                    resp.status_code, document_url,
                )
                return None
            image_bytes = resp.content
    except httpx.HTTPError as e:
        logger.warning("ocr_license_number: download error: %s", e)
        return None

    # 2)+3) OCR + 번호 추출
    number = await extract_credential_number(image_bytes, doc_type)
    if number:
        logger.info(
            "ocr_license_number: extracted doc_type=%s number=%s",
            doc_type, number,
        )
    else:
        logger.info(
            "ocr_license_number: no match (url=%s doc_type=%s)",
            document_url, doc_type,
        )
    return number


async def external_license_lookup(field: str, license_number: str) -> dict | None:
    """외부 API 로 자격번호 유효성을 조회한다 (placeholder).

    예시 연동처:
      - 대한변호사협회 (law)
      - 보건복지부 의사/간호사 면허 검색 (medical)
      - 한국공인회계사회 (finance:accounting)

    실제 API 가 붙기 전까지는 None 반환 → 관리자 수동 검증 필수.
    """
    if not _is_supported_field(field) or not license_number:
        return None
    logger.info(
        "external_license_lookup: placeholder field=%s license=%s",
        field, license_number,
    )
    return None


__all__ = [
    "EXPERT_FIELDS",
    "VERIFICATION_METHODS",
    "submit_credential",
    "verify_credential",
    "reject_credential",
    "list_pending_credentials",
    "is_expert_in",
    "get_expert_multiplier",
    "field_match",
    "expire_credentials",
    "revoke_credential",
    "list_experts_by_field",
    "ocr_license_number",
    "extract_credential_number",
    "external_license_lookup",
    "stats_by_field",
    "OCR_AVAILABLE",
]
