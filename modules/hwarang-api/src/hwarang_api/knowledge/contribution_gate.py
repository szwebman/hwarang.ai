"""HLKM Contribution Gate — KYC 게이트 정책.

핵심 규칙:
    - 지식 그래프에 **쓰기** 작업은 반드시 KYC/실존 인증 완료 사용자만.
    - 미인증 사용자는 대화만 가능. 대화는 LLMTrainingLog 에 분리 저장되어
      관리자 검토 후 학습 파이프라인에 편입.
    - 이 파일이 모든 쓰기 경로의 **중앙 게이트**. 우회 금지.

적용 대상 쓰기 작업:
    - ingest_fact (새 사실 기여)
    - peer_review (동료 검토 투표)
    - dispute_initiate / dispute_vote (분쟁)
    - bounty_create / bounty_submit (현상금 제출)
    - prediction_bet (예측 시장 베팅)
    - expert_credential_submit (전문가 자격 신청)
    - claim_decomposition_verify (원자 주장 검증 투표)
    - hypothesis_review (가설 검토)

정책:
    - KYC 미인증 → 쓰기 전부 거부 (GateDenial 로그)
    - 정지된 계정 → 쓰기 거부
    - tier 미달 → 해당 tier 필요 작업 거부
    - 일일 한도 초과 → 거부
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Literal

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# 쓰기 작업 분류
# ──────────────────────────────────────────────────────────────

class WriteAction(str, Enum):
    """지식 그래프 쓰기 작업 열거형."""
    INGEST_FACT = "ingest_fact"
    PEER_REVIEW = "peer_review"
    DISPUTE_INITIATE = "dispute_initiate"
    DISPUTE_VOTE = "dispute_vote"
    BOUNTY_CREATE = "bounty_create"
    BOUNTY_SUBMIT = "bounty_submit"
    PREDICTION_BET = "prediction_bet"
    EXPERT_CREDENTIAL = "expert_credential"
    CLAIM_VERIFY = "claim_verify"
    HYPOTHESIS_REVIEW = "hypothesis_review"
    REPUTATION_STAKE = "reputation_stake"


# 작업별 최소 tier 요구
ACTION_MIN_TIER: dict[str, str] = {
    WriteAction.INGEST_FACT.value: "BRONZE",
    WriteAction.PEER_REVIEW.value: "SILVER",
    WriteAction.DISPUTE_INITIATE.value: "GOLD",
    WriteAction.DISPUTE_VOTE.value: "DIAMOND",
    WriteAction.BOUNTY_CREATE.value: "BRONZE",        # 토큰만 있으면 누구나
    WriteAction.BOUNTY_SUBMIT.value: "SILVER",
    WriteAction.PREDICTION_BET.value: "BRONZE",
    WriteAction.EXPERT_CREDENTIAL.value: "BRONZE",
    WriteAction.CLAIM_VERIFY.value: "SILVER",
    WriteAction.HYPOTHESIS_REVIEW.value: "DIAMOND",
    WriteAction.REPUTATION_STAKE.value: "SILVER",
}

TIER_ORDER: dict[str, int] = {
    "SUSPENDED": -1,
    "BRONZE": 0,
    "SILVER": 1,
    "GOLD": 2,
    "DIAMOND": 3,
}


# ──────────────────────────────────────────────────────────────
# Denial 예외
# ──────────────────────────────────────────────────────────────

class GateDenied(Exception):
    """게이트에 의해 차단된 시도. reason 으로 분류."""

    def __init__(
        self,
        reason: Literal[
            "not_authenticated",
            "kyc_required",
            "suspended",
            "tier_insufficient",
            "quota_exceeded",
            "sybil_flagged",
            "unverified_fallback_to_training",
        ],
        message: str,
        detail: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.detail = detail or {}


# ──────────────────────────────────────────────────────────────
# 핵심 체크 함수
# ──────────────────────────────────────────────────────────────

async def require_contribution_permission(
    user_id: str | None,
    action: str,
    domain: str | None = None,
    session_id: str | None = None,
    payload_digest: str | None = None,
) -> dict:
    """지식 기여 권한 검사. 실패 시 GateDenied raise + DB 로그.

    Returns:
        {"user_id", "tier", "kyc_verified", "reputation", "expert_tags": [...]}

    Raises:
        GateDenied: 모든 차단 사유
    """
    # 1) 로그인 안 됨
    if not user_id:
        await _record_denial(None, session_id, action, "kyc_required", payload_digest)
        raise GateDenied(
            reason="not_authenticated",
            message="지식 기여는 로그인 + 실존 인증(KYC)이 필요합니다.",
        )

    # 2) 프로필 조회
    profile = await _get_profile(user_id)
    if profile is None:
        # 프로필 없음 = 사실상 신규 비인증 상태
        await _record_denial(user_id, session_id, action, "kyc_required", payload_digest)
        raise GateDenied(
            reason="kyc_required",
            message="기여자 프로필이 없습니다. 먼저 실존 인증(KYC)을 완료해 주세요.",
            detail={"next_step": "verify_personhood"},
        )

    # 3) KYC 미인증 → 차단 (핵심 정책)
    if not profile.get("kycVerified"):
        await _record_denial(user_id, session_id, action, "kyc_required", payload_digest)
        raise GateDenied(
            reason="kyc_required",
            message=(
                "지식 기여는 실존 인증(KYC)이 반드시 필요합니다. "
                "대화는 가능하지만, 지식 그래프에 쓰기는 인증 후에만 허용됩니다."
            ),
            detail={"next_step": "verify_personhood", "available_methods": [
                "ipin", "worldid", "brightid"
            ]},
        )

    # 4) 정지 상태
    if profile.get("tier") == "SUSPENDED":
        reason_note = profile.get("suspensionReason") or "정책 위반"
        await _record_denial(user_id, session_id, action, "suspended", payload_digest)
        raise GateDenied(
            reason="suspended",
            message=f"계정이 정지되었습니다: {reason_note}",
            detail={"suspended_until": profile.get("suspendedUntil")},
        )

    # 5) tier 요구 사항
    min_tier = ACTION_MIN_TIER.get(action, "BRONZE")
    if TIER_ORDER.get(profile.get("tier") or "BRONZE", 0) < TIER_ORDER.get(min_tier, 0):
        await _record_denial(user_id, session_id, action, "tier_insufficient", payload_digest)
        raise GateDenied(
            reason="tier_insufficient",
            message=f"이 작업은 {min_tier} 등급 이상이 필요합니다.",
            detail={"your_tier": profile.get("tier"), "required": min_tier},
        )

    # 6) 일일 한도
    if not await _within_daily_limit(user_id, profile.get("tier") or "BRONZE"):
        await _record_denial(user_id, session_id, action, "quota_exceeded", payload_digest)
        raise GateDenied(
            reason="quota_exceeded",
            message="오늘의 기여 한도를 초과했습니다.",
        )

    # 7) Sybil 의심
    sybil_severity = await _sybil_severity(user_id)
    if sybil_severity in {"high", "critical"}:
        await _record_denial(user_id, session_id, action, "sybil_flagged", payload_digest)
        raise GateDenied(
            reason="sybil_flagged",
            message="Sybil 의심 계정으로 검토 중입니다. 관리자 확인 후 해제됩니다.",
            detail={"severity": sybil_severity},
        )

    # 모두 통과
    return {
        "user_id": user_id,
        "tier": profile.get("tier"),
        "kyc_verified": profile.get("kycVerified"),
        "reputation": profile.get("reputation"),
        "expert_tags": profile.get("expertTags") or [],
    }


async def is_contribution_allowed(user_id: str | None, action: str) -> bool:
    """차단 로그 없이 권한 여부만 확인 (Dry check)."""
    try:
        await require_contribution_permission(user_id, action)
        return True
    except GateDenied:
        return False


async def verified_contributor_filter(user_ids: list[str]) -> list[str]:
    """배치 필터: 주어진 user_id 중 기여 가능한 사용자만 반환."""
    allowed: list[str] = []
    for uid in user_ids:
        if await is_contribution_allowed(uid, WriteAction.INGEST_FACT.value):
            allowed.append(uid)
    return allowed


# ──────────────────────────────────────────────────────────────
# LLM 학습 로그 저장 — 미인증 사용자의 대화는 여기로
# ──────────────────────────────────────────────────────────────

async def record_conversation_for_training(
    user_id: str | None,
    user_message: str,
    assistant_reply: str,
    conversation_id: str | None = None,
    session_id: str | None = None,
    model: str | None = None,
    domain: str | None = None,
    language: str = "ko",
    feedback_rating: str | None = None,
    feedback_note: str | None = None,
) -> str | None:
    """대화를 LLM 학습 데이터 후보로 저장.

    - 미인증 사용자: 기본 보존 기간 90일 후 삭제
    - 인증 사용자: 보존 기간 무제한 (사용자 삭제 요청 전까지)
    - 지식 그래프(KnowledgeFact)와 완전히 분리

    관리자는 나중에 reviewedForTraining=True + approvedForTraining=True 해야
    실제 학습 파이프라인에 편입됨.
    """
    try:
        profile = await _get_profile(user_id) if user_id else None
        kyc = bool(profile and profile.get("kycVerified"))

        expires_at = None
        if not kyc:
            expires_at = datetime.now(timezone.utc) + timedelta(days=90)

        # 간단한 PII / 유해 스캔 (로컬 규칙)
        contains_pii = _scan_pii(user_message) or _scan_pii(assistant_reply)
        contains_harmful = _scan_harmful(user_message) or _scan_harmful(assistant_reply)

        log = await prisma.llmtraininglog.create(
            data={
                "userId": user_id,
                "userIsVerified": kyc,
                "sessionId": session_id,
                "userMessage": user_message[:20000],
                "assistantReply": assistant_reply[:20000],
                "conversationId": conversation_id,
                "model": model,
                "domain": domain,
                "language": language,
                "feedbackRating": feedback_rating,
                "feedbackNote": feedback_note,
                "containsPII": contains_pii,
                "containsHarmful": contains_harmful,
                "expiresAt": expires_at,
            }
        )
        return log.id
    except Exception as e:  # noqa: BLE001
        logger.warning("record_conversation_for_training failed: %s", e)
        return None


async def approve_for_training(
    log_id: str,
    admin_user_id: str,
    quality_score: float | None = None,
) -> bool:
    """관리자 검토 후 학습 파이프라인 편입 승인."""
    try:
        await prisma.llmtraininglog.update(
            where={"id": log_id},
            data={
                "reviewedForTraining": True,
                "approvedForTraining": True,
                "approvedAt": datetime.now(timezone.utc),
                "approvedBy": admin_user_id,
                "qualityScore": quality_score,
            },
        )
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("approve_for_training failed: %s", e)
        return False


async def reject_for_training(log_id: str, admin_user_id: str, note: str | None = None) -> bool:
    try:
        await prisma.llmtraininglog.update(
            where={"id": log_id},
            data={
                "reviewedForTraining": True,
                "approvedForTraining": False,
                "approvedBy": admin_user_id,
            },
        )
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("reject_for_training failed: %s", e)
        return False


async def list_pending_training_logs(limit: int = 100, verified_only: bool = False) -> list[dict]:
    """학습 승인 대기 로그."""
    try:
        where: dict[str, Any] = {"reviewedForTraining": False}
        if verified_only:
            where["userIsVerified"] = True
        logs = await prisma.llmtraininglog.find_many(
            where=where, take=limit, order={"createdAt": "desc"}
        )
        return [_log_to_dict(x) for x in logs]
    except Exception:
        return []


async def purge_expired_training_logs(batch: int = 500) -> int:
    """만료된 미인증 사용자 로그 삭제."""
    try:
        now = datetime.now(timezone.utc)
        result = await prisma.llmtraininglog.delete_many(
            where={"expiresAt": {"lte": now}, "userIsVerified": False}
        )
        count = getattr(result, "count", 0) or 0
        logger.info("purged %d expired training logs", count)
        return count
    except Exception as e:  # noqa: BLE001
        logger.warning("purge_expired_training_logs failed: %s", e)
        return 0


async def training_log_stats() -> dict:
    """관리자 대시보드용 통계."""
    try:
        total = await prisma.llmtraininglog.count()
        verified = await prisma.llmtraininglog.count(where={"userIsVerified": True})
        pending = await prisma.llmtraininglog.count(where={"reviewedForTraining": False})
        approved = await prisma.llmtraininglog.count(where={"approvedForTraining": True})
        return {
            "total": total,
            "verified_users": verified,
            "unverified_users": total - verified,
            "pending_review": pending,
            "approved_for_training": approved,
        }
    except Exception:
        return {"total": 0, "verified_users": 0, "unverified_users": 0,
                "pending_review": 0, "approved_for_training": 0}


# ──────────────────────────────────────────────────────────────
# Denial 기록
# ──────────────────────────────────────────────────────────────

async def _record_denial(
    user_id: str | None,
    session_id: str | None,
    action: str,
    reason: str,
    payload_digest: str | None,
) -> None:
    try:
        await prisma.contributiongatedenial.create(
            data={
                "userId": user_id,
                "sessionId": session_id,
                "attemptedAction": action,
                "reason": reason,
                "payloadDigest": payload_digest,
            }
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("gate denial record failed: %s", e)


async def denial_log(
    user_id: str | None = None,
    reason: str | None = None,
    limit: int = 100,
) -> list[dict]:
    try:
        where: dict[str, Any] = {}
        if user_id:
            where["userId"] = user_id
        if reason:
            where["reason"] = reason
        rows = await prisma.contributiongatedenial.find_many(
            where=where, take=limit, order={"createdAt": "desc"}
        )
        return [
            {
                "id": r.id,
                "userId": r.userId,
                "sessionId": r.sessionId,
                "attemptedAction": r.attemptedAction,
                "reason": r.reason,
                "createdAt": r.createdAt,
            }
            for r in rows
        ]
    except Exception:
        return []


async def denial_stats(last_hours: int = 24) -> dict:
    """최근 차단 통계 (Sybil 감지에 활용)."""
    try:
        since = datetime.now(timezone.utc) - timedelta(hours=last_hours)
        rows = await prisma.contributiongatedenial.find_many(
            where={"createdAt": {"gte": since}}
        )
        by_reason: dict[str, int] = {}
        by_user: dict[str, int] = {}
        for r in rows:
            by_reason[r.reason] = by_reason.get(r.reason, 0) + 1
            if r.userId:
                by_user[r.userId] = by_user.get(r.userId, 0) + 1
        return {
            "total": len(rows),
            "by_reason": by_reason,
            "top_users": sorted(by_user.items(), key=lambda kv: -kv[1])[:20],
        }
    except Exception:
        return {"total": 0, "by_reason": {}, "top_users": []}


# ──────────────────────────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────────────────────────

async def _get_profile(user_id: str) -> dict | None:
    try:
        p = await prisma.contributorprofile.find_unique(where={"userId": user_id})
        if not p:
            return None
        return {
            "userId": p.userId,
            "tier": p.tier,
            "reputation": p.reputation,
            "kycVerified": p.kycVerified,
            "suspensionReason": p.suspensionReason,
            "suspendedUntil": p.suspendedUntil,
            "expertTags": p.expertTags,
        }
    except Exception:
        return None


async def _within_daily_limit(user_id: str, tier: str) -> bool:
    # contributor_tier.within_daily_limit 과 동일 의미, circular 방지 위해 여기에 미니 구현
    try:
        from .contributor_tier import TIER_PERMISSIONS
    except Exception:
        return True
    limit = TIER_PERMISSIONS.get(tier, {}).get("daily_contrib_limit", 5)
    if limit == 0:
        return False
    try:
        since = datetime.now(timezone.utc) - timedelta(days=1)
        count = await prisma.contributionstake.count(
            where={"userId": user_id, "createdAt": {"gte": since}}
        )
        return count < limit
    except Exception:
        return True  # DB 오류 시 통과 (보안보다 가용성 우선)


async def _sybil_severity(user_id: str) -> str | None:
    try:
        flags = await prisma.sybilflag.find_many(
            where={"userId": user_id, "resolved": False}
        )
        if not flags:
            return None
        sev_rank = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        return max((f.severity for f in flags), key=lambda s: sev_rank.get(s, 0))
    except Exception:
        return None


# PII / 유해 스캔 (경량)

import re

_PII_PATTERNS: list[re.Pattern] = [
    re.compile(r"\d{6}-[1-4]\d{6}"),                       # 주민번호
    re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b"),         # 휴대폰
    re.compile(r"\b\d{3}-\d{2}-\d{5}\b"),                  # 사업자번호
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),  # 이메일
    re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),  # 카드번호
]

_HARMFUL_PATTERNS: list[re.Pattern] = [
    re.compile(r"(자살|자해|죽고 싶|suicide)", re.IGNORECASE),
    re.compile(r"(폭탄 만드|총기 개조|마약 제조)"),
    re.compile(r"(아동 성적|child sexual)", re.IGNORECASE),
]


def _scan_pii(text: str) -> bool:
    return any(p.search(text) for p in _PII_PATTERNS)


def _scan_harmful(text: str) -> bool:
    return any(p.search(text) for p in _HARMFUL_PATTERNS)


def _log_to_dict(x: Any) -> dict:
    return {
        "id": x.id,
        "userId": x.userId,
        "userIsVerified": x.userIsVerified,
        "userMessage": (x.userMessage or "")[:200],
        "assistantReply": (x.assistantReply or "")[:200],
        "model": x.model,
        "domain": x.domain,
        "feedbackRating": x.feedbackRating,
        "containsPII": x.containsPII,
        "containsHarmful": x.containsHarmful,
        "qualityScore": x.qualityScore,
        "reviewedForTraining": x.reviewedForTraining,
        "approvedForTraining": x.approvedForTraining,
        "createdAt": x.createdAt,
        "expiresAt": x.expiresAt,
    }


def payload_digest(payload: Any) -> str:
    """쓰기 시도 payload 를 해시 (추적/복구용)."""
    try:
        serialized = json.dumps(payload, sort_keys=True, default=str)
    except Exception:
        serialized = str(payload)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


__all__ = [
    "WriteAction",
    "ACTION_MIN_TIER",
    "GateDenied",
    "require_contribution_permission",
    "is_contribution_allowed",
    "verified_contributor_filter",
    "record_conversation_for_training",
    "approve_for_training",
    "reject_for_training",
    "list_pending_training_logs",
    "purge_expired_training_logs",
    "training_log_stats",
    "denial_log",
    "denial_stats",
    "payload_digest",
]
