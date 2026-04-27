"""HLKM - Proof of Personhood (실존 인증).

외부 KYC / 신원 제공자와 연동해 "1인 = 1계정" 을 보장한다.
시빌 방어의 최후 관문.

지원 method:
  - `ipin`            — 한국 I-PIN / 휴대폰 본인확인 (PASS 연동 placeholder)
  - `worldid`         — Worldcoin World ID (orb verification)
  - `brightid`        — BrightID social graph
  - `proofofhumanity` — Proof of Humanity (on-chain)
  - `manual`          — 관리자 수동 승인

환경 변수 (실제 연동 시 설정):
  HWARANG_POP_IPIN_API_KEY
  HWARANG_POP_WORLDID_APP_ID
  HWARANG_POP_BRIGHTID_CONTEXT
  HWARANG_POP_POH_RPC

의존:
  - `hwarang_api.db.prisma`
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma

from .types import KnowledgeFact  # noqa: F401 (공개 API 타입 안정화)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────
SUPPORTED_METHODS: list[str] = [
    "ipin",
    "worldid",
    "brightid",
    "proofofhumanity",
    "manual",
]

# method 별 만료일 (연간 재인증 강제)
_VERIFICATION_TTL_DAYS: dict[str, int] = {
    "ipin": 365,
    "worldid": 365 * 2,
    "brightid": 180,
    "proofofhumanity": 365,
    "manual": 365,
}

_UNIQUENESS_SALT = os.getenv("HWARANG_POP_UNIQ_SALT", "hwarang-pop-v1")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uniqueness_hash(method: str, provider_id: str) -> str:
    """method + provider_id 의 HMAC-SHA256 해시.

    한 사람이 같은 provider ID 로 여러 계정을 만들 수 없게
    중복 체크용 식별자. salt 는 환경변수로 관리.
    """
    msg = f"{method}:{provider_id}".encode("utf-8")
    return hmac.new(_UNIQUENESS_SALT.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:40]


async def check_uniqueness(method: str, provider_id: str) -> bool:
    """동일 uniqueness_hash 가 이미 다른 user 에게 등록돼 있으면 False."""
    uh = _uniqueness_hash(method, provider_id)
    existing = await prisma.personhoodverification.find_first(
        where={"providerId": uh, "revoked": False}
    )
    return existing is None


# ─────────────────────────────────────────────
# 외부 제공자 검증 (실제 API 는 placeholder)
# ─────────────────────────────────────────────
async def _verify_ipin(proof: str) -> tuple[bool, str | None]:
    """I-PIN / 휴대폰 본인확인 검증.

    실제 환경에서는 NICE / KCB / PASS API 호출.
    proof 포맷: "token|ci_hash" — ci(연계정보) 해시 반환.
    """
    api_key = os.getenv("HWARANG_POP_IPIN_API_KEY")
    if not api_key:
        logger.info("ipin provider disabled (no API key) — stub verify")
        if not proof or ":" not in proof:
            return (False, None)
        _, ci = proof.split(":", 1)
        return (True, ci[:64])
    # TODO: 실제 PASS/NICE API 호출
    return (True, proof.split(":", 1)[-1][:64])


async def _verify_worldid(proof: str) -> tuple[bool, str | None]:
    """World ID Cloud Verification API 호출 (placeholder).

    proof 포맷: Semaphore zk-proof JSON 문자열.
    """
    app_id = os.getenv("HWARANG_POP_WORLDID_APP_ID")
    if not app_id:
        logger.info("worldid disabled — stub verify")
        if not proof or len(proof) < 16:
            return (False, None)
        nullifier = hashlib.sha256(proof.encode()).hexdigest()[:40]
        return (True, nullifier)
    # TODO: POST https://developer.worldcoin.org/api/v2/verify/{app_id}
    nullifier = hashlib.sha256(proof.encode()).hexdigest()[:40]
    return (True, nullifier)


async def _verify_brightid(proof: str) -> tuple[bool, str | None]:
    """BrightID context 검증 (placeholder).

    proof 포맷: "contextId|signature".
    """
    context = os.getenv("HWARANG_POP_BRIGHTID_CONTEXT")
    if not context:
        logger.info("brightid disabled — stub verify")
        if "|" not in proof:
            return (False, None)
        ctx_id, _sig = proof.split("|", 1)
        return (True, ctx_id[:64])
    # TODO: GET https://app.brightid.org/node/v6/verifications/{context}/{contextId}
    return (True, proof.split("|", 1)[0][:64])


async def _verify_proofofhumanity(proof: str) -> tuple[bool, str | None]:
    """Proof of Humanity on-chain 조회 (placeholder).

    proof 포맷: Ethereum address (0x...).
    """
    rpc = os.getenv("HWARANG_POP_POH_RPC")
    if not proof.startswith("0x") or len(proof) != 42:
        return (False, None)
    if not rpc:
        logger.info("poh disabled — stub verify")
        return (True, proof.lower())
    # TODO: PoH contract isRegistered(address) 호출
    return (True, proof.lower())


_METHOD_DISPATCH = {
    "ipin": _verify_ipin,
    "worldid": _verify_worldid,
    "brightid": _verify_brightid,
    "proofofhumanity": _verify_proofofhumanity,
}


# ─────────────────────────────────────────────
# 검증 시작 / 완료
# ─────────────────────────────────────────────
async def start_verification(user_id: str, method: str) -> dict:
    """해당 method 의 제공자에게 challenge 요청.

    반환 스키마 (method 별):
      - ipin:            {"challenge", "redirect_url"}
      - worldid:         {"challenge", "action", "app_id"}
      - brightid:        {"qr_code", "deep_link", "context_id"}
      - proofofhumanity: {"challenge", "eth_rpc_hint"}
      - manual:          {"challenge", "note": "contact admin"}
    """
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"unsupported method: {method}")

    challenge = secrets.token_urlsafe(24)
    session_key = f"pop:{user_id}:{method}:{challenge}"

    if method == "ipin":
        return {
            "challenge": challenge,
            "redirect_url": f"/auth/ipin/start?session={session_key}",
            "session_key": session_key,
        }
    if method == "worldid":
        return {
            "challenge": challenge,
            "action": "hwarang-pop",
            "app_id": os.getenv("HWARANG_POP_WORLDID_APP_ID", "app_stub"),
            "session_key": session_key,
        }
    if method == "brightid":
        ctx = os.getenv("HWARANG_POP_BRIGHTID_CONTEXT", "Hwarang")
        return {
            "qr_code": f"brightid://link-verification/http:%2f%2fnode.brightid.org/{ctx}/{challenge}",
            "deep_link": f"brightid://link-verification/{ctx}/{challenge}",
            "context_id": challenge,
            "session_key": session_key,
        }
    if method == "proofofhumanity":
        return {
            "challenge": challenge,
            "eth_rpc_hint": os.getenv("HWARANG_POP_POH_RPC", "https://mainnet.infura.io"),
            "session_key": session_key,
        }
    return {
        "challenge": challenge,
        "note": "manual verification requires admin approval",
        "session_key": session_key,
    }


async def complete_verification(
    user_id: str, method: str, proof: str
) -> dict:
    """제공자로부터 받은 proof 를 검증하고 저장.

    - method 별 검증 함수 호출.
    - 성공 시:
        - uniqueness 체크 (다른 user 가 이미 등록 X).
        - PersonhoodVerification insert.
        - ContributorProfile.kycVerified=True.
    - 반환: {"verified": bool, "method", "provider_id", "reason"?}
    """
    if method not in SUPPORTED_METHODS:
        return {"verified": False, "method": method, "reason": "unsupported_method"}
    if method == "manual":
        return {
            "verified": False,
            "method": method,
            "reason": "use verify_manual for manual method",
        }

    verifier = _METHOD_DISPATCH.get(method)
    if verifier is None:
        return {"verified": False, "method": method, "reason": "no_dispatch"}

    ok, provider_id = await verifier(proof)
    if not ok or not provider_id:
        return {"verified": False, "method": method, "reason": "provider_rejected"}

    uh = _uniqueness_hash(method, provider_id)
    # 중복 체크 (자기 자신은 허용: 갱신)
    existing = await prisma.personhoodverification.find_first(
        where={"providerId": uh, "revoked": False}
    )
    if existing is not None and existing.userId != user_id:
        return {
            "verified": False,
            "method": method,
            "reason": "provider_id_already_used",
        }

    ttl = _VERIFICATION_TTL_DAYS.get(method, 365)
    now = _utcnow()
    expires = now + timedelta(days=ttl)

    await prisma.personhoodverification.upsert(
        where={"userId": user_id},
        data={
            "create": {
                "userId": user_id,
                "method": method,
                "providerId": uh,
                "proof": hashlib.sha256(proof.encode()).hexdigest()[:64],
                "verifiedAt": now,
                "expiresAt": expires,
                "revoked": False,
            },
            "update": {
                "method": method,
                "providerId": uh,
                "proof": hashlib.sha256(proof.encode()).hexdigest()[:64],
                "verifiedAt": now,
                "expiresAt": expires,
                "revoked": False,
                "revokedReason": None,
            },
        },
    )
    await prisma.contributorprofile.upsert(
        where={"userId": user_id},
        data={
            "create": {
                "userId": user_id,
                "kycVerified": True,
                "kycMethod": method,
                "kycVerifiedAt": now,
            },
            "update": {
                "kycVerified": True,
                "kycMethod": method,
                "kycVerifiedAt": now,
            },
        },
    )

    logger.info("pop verified: user=%s method=%s", user_id, method)
    return {
        "verified": True,
        "method": method,
        "provider_id": uh,
        "expires_at": expires.isoformat(),
    }


# ─────────────────────────────────────────────
# 관리자 수동 승인 / 취소
# ─────────────────────────────────────────────
async def verify_manual(
    user_id: str, admin_id: str, document_hash: str, note: str
) -> dict:
    """마지막 수단: 관리자가 신분증 사본 등으로 수동 승인.

    document_hash: 원본 문서의 해시 (원본 저장 X, 감사용 해시만).
    """
    if not admin_id or not document_hash:
        raise ValueError("admin_id and document_hash required")
    now = _utcnow()
    expires = now + timedelta(days=_VERIFICATION_TTL_DAYS["manual"])
    provider_id = _uniqueness_hash("manual", document_hash)

    await prisma.personhoodverification.upsert(
        where={"userId": user_id},
        data={
            "create": {
                "userId": user_id,
                "method": "manual",
                "providerId": provider_id,
                "proof": f"admin:{admin_id}|doc:{document_hash[:32]}|note:{note[:200]}",
                "verifiedAt": now,
                "expiresAt": expires,
                "revoked": False,
            },
            "update": {
                "method": "manual",
                "providerId": provider_id,
                "proof": f"admin:{admin_id}|doc:{document_hash[:32]}|note:{note[:200]}",
                "verifiedAt": now,
                "expiresAt": expires,
                "revoked": False,
                "revokedReason": None,
            },
        },
    )
    await prisma.contributorprofile.upsert(
        where={"userId": user_id},
        data={
            "create": {
                "userId": user_id,
                "kycVerified": True,
                "kycMethod": "manual",
                "kycVerifiedAt": now,
            },
            "update": {
                "kycVerified": True,
                "kycMethod": "manual",
                "kycVerifiedAt": now,
            },
        },
    )
    logger.info("manual pop verified: user=%s admin=%s", user_id, admin_id)
    return {
        "verified": True,
        "method": "manual",
        "provider_id": provider_id,
        "admin_id": admin_id,
        "expires_at": expires.isoformat(),
    }


async def revoke_verification(user_id: str, reason: str) -> None:
    """사기 발각 등 사유로 인증 취소.

    PersonhoodVerification.revoked=True, ContributorProfile.kycVerified=False.
    """
    await prisma.personhoodverification.update(
        where={"userId": user_id},
        data={
            "revoked": True,
            "revokedReason": reason[:480],
        },
    )
    await prisma.contributorprofile.update(
        where={"userId": user_id},
        data={"kycVerified": False},
    )
    logger.warning("pop revoked: user=%s reason=%s", user_id, reason)


# ─────────────────────────────────────────────
# 조회
# ─────────────────────────────────────────────
async def is_verified(user_id: str) -> bool:
    """현재 유효한 인증이 있는지 확인.

    조건: 레코드 존재 + revoked=False + expiresAt 미도래.
    """
    row = await prisma.personhoodverification.find_unique(where={"userId": user_id})
    if row is None or row.revoked:
        return False
    if row.expiresAt and row.expiresAt <= _utcnow():
        return False
    return True


async def list_verifications(
    method: str | None = None, revoked: bool = False
) -> list[dict]:
    """관리자 UI 용 인증 목록 조회."""
    where: dict[str, Any] = {"revoked": revoked}
    if method:
        where["method"] = method
    rows = await prisma.personhoodverification.find_many(
        where=where, take=500, order={"verifiedAt": "desc"}
    )
    out: list[dict] = []
    now = _utcnow()
    for r in rows:
        expired = bool(r.expiresAt and r.expiresAt <= now)
        out.append(
            {
                "user_id": r.userId,
                "method": r.method,
                "provider_id": r.providerId,
                "verified_at": r.verifiedAt,
                "expires_at": r.expiresAt,
                "revoked": r.revoked,
                "revoked_reason": r.revokedReason,
                "expired": expired,
            }
        )
    return out


__all__ = [
    "SUPPORTED_METHODS",
    "start_verification",
    "complete_verification",
    "verify_manual",
    "revoke_verification",
    "is_verified",
    "list_verifications",
    "check_uniqueness",
    "_uniqueness_hash",
    "_verify_ipin",
    "_verify_worldid",
    "_verify_brightid",
    "_verify_proofofhumanity",
]
