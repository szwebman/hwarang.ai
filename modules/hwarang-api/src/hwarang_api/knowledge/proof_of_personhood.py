"""HLKM - Proof of Personhood (실존 인증).

외부 KYC / 신원 제공자와 연동해 "1인 = 1계정" 을 보장한다.
시빌 방어의 최후 관문.

지원 method:
  - `ipin`            — 한국 I-PIN / 휴대폰 본인확인 (PASS/NICE)
  - `worldid`         — Worldcoin World ID (orb verification)
  - `brightid`        — BrightID social graph
  - `proofofhumanity` — Proof of Humanity (on-chain)
  - `manual`          — 관리자 수동 승인

환경 변수 (실제 연동 시 설정):
  HWARANG_POP_PASS_API_KEY        — PASS/NICE API key (ipin)
  HWARANG_POP_PASS_CLIENT_ID      — PASS/NICE client id (ipin)
  HWARANG_POP_PASS_ENDPOINT       — PASS/NICE endpoint (default nice.checkplus.co.kr)
  HWARANG_POP_WORLDID_APP_ID      — World ID Cloud Verification app_id
  HWARANG_POP_WORLDID_API_KEY     — World ID API key (optional Bearer)
  HWARANG_POP_WORLDID_ACTION      — action label (default: hwarang-pop)
  HWARANG_POP_BRIGHTID_CONTEXT    — BrightID context name (e.g. "Hwarang")
  HWARANG_POP_POH_RPC_URL         — Ethereum RPC URL (PoH 컨트랙트 조회)
  HWARANG_POP_POH_CONTRACT_ADDR   — PoH 컨트랙트 주소 (default mainnet 공식)

의존:
  - `hwarang_api.db.prisma`
  - `httpx` (HTTP), `web3` (PoH; optional)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from hwarang_api.db import prisma

from .types import KnowledgeFact  # noqa: F401 (공개 API 타입 안정화)

logger = logging.getLogger(__name__)


# web3 는 선택 의존: 없으면 PoH stub fallback
try:
    from web3 import Web3  # type: ignore
    _WEB3_AVAILABLE = True
except ImportError:  # pragma: no cover
    Web3 = None  # type: ignore
    _WEB3_AVAILABLE = False


_POH_DEFAULT_CONTRACT = "0xC5E9dDebb09Cd64DfaCab4011A0D5cEDaf7c9BDb"  # PoH v1 mainnet
_POH_ABI_IS_REGISTERED = [
    {
        "inputs": [{"internalType": "address", "name": "_submissionID", "type": "address"}],
        "name": "isRegistered",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    }
]


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
    """I-PIN / 휴대폰 본인확인 검증 (PASS / NICE).

    proof 포맷: "request_id:ci" — request_id 와 CI(연계정보) 콜론 구분.
    실제 PASS/NICE API 는 비공개 spec 이라 일반 form-based 호출로 작성.
    환경변수:
      HWARANG_POP_PASS_API_KEY     (Bearer)
      HWARANG_POP_PASS_CLIENT_ID
      HWARANG_POP_PASS_ENDPOINT    (default https://nice.checkplus.co.kr/api/verify)
    """
    api_key = os.getenv("HWARANG_POP_PASS_API_KEY")
    client_id = os.getenv("HWARANG_POP_PASS_CLIENT_ID")
    endpoint = os.getenv(
        "HWARANG_POP_PASS_ENDPOINT", "https://nice.checkplus.co.kr/api/verify"
    )
    if not (api_key and client_id):
        logger.info("ipin provider disabled (no API key) — stub verify")
        if not proof or ":" not in proof:
            return (False, None)
        _, ci = proof.split(":", 1)
        return (True, ci[:64])

    if not proof or ":" not in proof:
        return (False, None)
    request_id, user_ci = proof.split(":", 1)

    # NOTE: 실제 PASS/NICE 운영 spec 은 NDA 기반. 아래는 일반 form-based 패턴.
    # TODO(prod): 운영 계약 후 정확한 endpoint / signature 알고리즘으로 교체.
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                endpoint,
                data={
                    "client_id": client_id,
                    "ci": user_ci,
                    "request_id": request_id,
                },
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError as e:
        logger.warning("ipin http error: %s", e)
        return (False, None)

    if resp.status_code != 200:
        logger.info("ipin reject: status=%s", resp.status_code)
        return (False, None)
    try:
        result = resp.json()
    except ValueError:
        return (False, None)
    verified = result.get("status") in ("ok", "success", "verified")
    ci_value = result.get("ci") or user_ci
    if not verified or not ci_value:
        return (False, None)
    return (True, str(ci_value)[:64])


async def _verify_worldid(proof: str) -> tuple[bool, str | None]:
    """World ID Cloud Verification API 호출.

    proof 포맷: JSON 문자열 — {"nullifier_hash", "merkle_root", "proof", "verification_level"?}.
    엔드포인트: POST https://developer.worldcoin.org/api/v2/verify/{app_id}
    환경변수:
      HWARANG_POP_WORLDID_APP_ID    (required)
      HWARANG_POP_WORLDID_API_KEY   (optional Bearer; 일부 액션은 필요)
      HWARANG_POP_WORLDID_ACTION    (default: hwarang-pop)
    """
    import json as _json

    app_id = os.getenv("HWARANG_POP_WORLDID_APP_ID")
    if not app_id:
        logger.info("worldid disabled — stub verify")
        if not proof or len(proof) < 16:
            return (False, None)
        nullifier = hashlib.sha256(proof.encode()).hexdigest()[:40]
        return (True, nullifier)

    try:
        payload = _json.loads(proof) if proof.lstrip().startswith("{") else None
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        logger.info("worldid: invalid proof payload (not JSON object)")
        return (False, None)

    nullifier_hash = payload.get("nullifier_hash")
    merkle_root = payload.get("merkle_root")
    zk_proof = payload.get("proof")
    if not (nullifier_hash and merkle_root and zk_proof):
        return (False, None)

    action = os.getenv("HWARANG_POP_WORLDID_ACTION", "hwarang-pop")
    api_key = os.getenv("HWARANG_POP_WORLDID_API_KEY")
    body = {
        "nullifier_hash": nullifier_hash,
        "merkle_root": merkle_root,
        "proof": zk_proof,
        "action": action,
    }
    if "verification_level" in payload:
        body["verification_level"] = payload["verification_level"]
    if "signal_hash" in payload:
        body["signal_hash"] = payload["signal_hash"]

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    url = f"https://developer.worldcoin.org/api/v2/verify/{app_id}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=body, headers=headers)
    except httpx.HTTPError as e:
        logger.warning("worldid http error: %s", e)
        return (False, None)

    if resp.status_code != 200:
        logger.info(
            "worldid reject: status=%s body=%s",
            resp.status_code, resp.text[:200],
        )
        return (False, None)
    # 성공 시 유일성 식별자는 nullifier_hash (action 별 고유)
    return (True, str(nullifier_hash)[:64])


async def _verify_brightid(proof: str) -> tuple[bool, str | None]:
    """BrightID 노드 verification 조회.

    proof 포맷: "contextId" 또는 "contextId|signature" (signature 는 클라이언트 사전 서명).
    엔드포인트: GET https://app.brightid.org/node/v6/verifications/{context}/{contextId}
    응답: {"data": {"unique": bool, "verifications": [...] }}  (노드 v6)
    환경변수:
      HWARANG_POP_BRIGHTID_CONTEXT  (e.g. "Hwarang")
      HWARANG_POP_BRIGHTID_NODE     (default https://app.brightid.org/node)
    """
    context = os.getenv("HWARANG_POP_BRIGHTID_CONTEXT")
    if not context:
        logger.info("brightid disabled — stub verify")
        if "|" not in proof and not proof:
            return (False, None)
        ctx_id = proof.split("|", 1)[0]
        if not ctx_id:
            return (False, None)
        return (True, ctx_id[:64])

    if not proof:
        return (False, None)
    ctx_id = proof.split("|", 1)[0].strip()
    if not ctx_id:
        return (False, None)

    node = os.getenv("HWARANG_POP_BRIGHTID_NODE", "https://app.brightid.org/node")
    url = f"{node.rstrip('/')}/v6/verifications/{context}/{ctx_id}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
    except httpx.HTTPError as e:
        logger.warning("brightid http error: %s", e)
        return (False, None)

    if resp.status_code != 200:
        logger.info(
            "brightid reject: status=%s body=%s",
            resp.status_code, resp.text[:200],
        )
        return (False, None)
    try:
        data = resp.json()
    except ValueError:
        return (False, None)
    inner = data.get("data") if isinstance(data, dict) else None
    if not isinstance(inner, dict):
        return (False, None)
    verifications = inner.get("verifications") or []
    unique = inner.get("unique", True)
    if not verifications or not unique:
        return (False, None)
    return (True, ctx_id[:64])


async def _verify_proofofhumanity(proof: str) -> tuple[bool, str | None]:
    """Proof of Humanity on-chain 조회.

    proof 포맷: Ethereum address (0x...).
    환경변수:
      HWARANG_POP_POH_RPC_URL         (required)
      HWARANG_POP_POH_CONTRACT_ADDR   (default PoH v1 mainnet)
    web3.py 가 없으면 stub 동작.
    """
    if not proof.startswith("0x") or len(proof) != 42:
        return (False, None)

    rpc = os.getenv("HWARANG_POP_POH_RPC_URL") or os.getenv("HWARANG_POP_POH_RPC")
    if not rpc:
        logger.info("poh disabled (no RPC URL) — stub verify")
        return (True, proof.lower())

    if not _WEB3_AVAILABLE:
        logger.warning("poh: web3.py not installed — stub verify")
        return (True, proof.lower())

    contract_addr = os.getenv("HWARANG_POP_POH_CONTRACT_ADDR", _POH_DEFAULT_CONTRACT)
    try:
        w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 10}))
        if not w3.is_connected():
            logger.warning("poh: web3 RPC connect failed")
            return (False, None)
        addr = Web3.to_checksum_address(proof)
        contract_addr_cs = Web3.to_checksum_address(contract_addr)
        contract = w3.eth.contract(address=contract_addr_cs, abi=_POH_ABI_IS_REGISTERED)
        registered = bool(contract.functions.isRegistered(addr).call())
    except Exception as e:  # pragma: no cover (네트워크 의존)
        logger.warning("poh on-chain call failed: %s", e)
        return (False, None)

    if not registered:
        return (False, None)
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
