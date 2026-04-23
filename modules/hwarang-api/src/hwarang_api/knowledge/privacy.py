"""HLKM C5 - 개인/공용 프라이버시 계층 + 차등 프라이버시.

제공 기능:
  - encrypt_for_user / decrypt_for_user : AES-256-GCM + HKDF(user_id salt)
  - store_private_fact / load_private_facts : 개인 전용 KnowledgeFact CRUD
  - add_dp_noise / dp_aggregate_counts : Laplace 메커니즘 기반 통계
  - redact_pii : 전화번호/주민번호/이메일 마스킹
  - audit_access : 접근 감사 로그 (stdout + DB 시도)

의존:
    cryptography (pip install cryptography)
"""

from __future__ import annotations

import base64
import hashlib
import logging
import math
import os
import random
import re
from collections import defaultdict
from datetime import datetime, timezone

from hwarang_api.db import prisma
from hwarang_api.knowledge.types import KnowledgeFact, KnowledgeVisibility

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Encryption (AES-256-GCM + HKDF)
# ─────────────────────────────────────────────
def _derive_key(master_key: bytes, user_id: str) -> bytes:
    """HKDF-SHA256 로 user 별 32바이트 키 유도.

    cryptography 가 있으면 HKDF 사용, 없으면 순수 hashlib fallback.
    """
    salt = hashlib.sha256(user_id.encode("utf-8")).digest()
    try:
        from cryptography.hazmat.primitives import hashes as _hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

        return HKDF(
            algorithm=_hashes.SHA256(),
            length=32,
            salt=salt,
            info=b"hlkm-user-key",
        ).derive(master_key)
    except Exception:
        # Fallback: HMAC 기반 확장(보안상 참고용).
        import hmac

        t1 = hmac.new(salt, master_key + b"hlkm-user-key-1", hashlib.sha256).digest()
        t2 = hmac.new(salt, t1 + b"hlkm-user-key-2", hashlib.sha256).digest()
        return (t1 + t2)[:32]


def encrypt_for_user(content: str, user_id: str, master_key: bytes) -> str:
    """AES-256-GCM 암호화. 반환 포맷: base64(nonce || ciphertext+tag)."""
    key = _derive_key(master_key, user_id)
    nonce = os.urandom(12)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    aes = AESGCM(key)
    ct = aes.encrypt(nonce, content.encode("utf-8"), user_id.encode("utf-8"))
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_for_user(encrypted_b64: str, user_id: str, master_key: bytes) -> str:
    """AES-256-GCM 복호화. auth tag 불일치 시 예외 그대로 전파."""
    key = _derive_key(master_key, user_id)
    raw = base64.b64decode(encrypted_b64)
    if len(raw) < 13:
        raise ValueError("ciphertext too short")
    nonce, ct = raw[:12], raw[12:]
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    aes = AESGCM(key)
    pt = aes.decrypt(nonce, ct, user_id.encode("utf-8"))
    return pt.decode("utf-8")


# ─────────────────────────────────────────────
# Private fact CRUD
# ─────────────────────────────────────────────
async def store_private_fact(
    fact: KnowledgeFact, user_id: str, master_key: bytes
) -> str:
    """개인 전용 팩트 저장. content 는 암호화되어 DB 에 들어간다.

    반환: 생성된 fact id.
    """
    encrypted = encrypt_for_user(fact.content, user_id, master_key)
    content_hash = hashlib.sha256(fact.content.encode("utf-8")).hexdigest()

    row = await prisma.knowledgefact.create(
        data={
            "content": encrypted,
            "contentHash": content_hash,
            "domain": fact.domain,
            "entity": fact.entity,
            "tags": fact.tags or [],
            "language": fact.language,
            "validFrom": fact.valid_from,
            "validTo": fact.valid_to,
            "confidenceT0": fact.confidence_t0,
            "halfLifeDays": fact.half_life_days,
            "status": fact.status.value,
            "source": fact.source or "private",
            "sourceUrl": fact.source_url,
            "sourceType": fact.source_type,
            "visibility": KnowledgeVisibility.PRIVATE.value,
            "ownerUserId": user_id,
        }
    )
    await audit_access(user_id, row.id, "store_private")
    return row.id


async def load_private_facts(
    user_id: str, master_key: bytes, query: str | None = None
) -> list[KnowledgeFact]:
    """사용자 본인의 private 팩트 로드 + 복호화.

    query 가 주어지면 domain/entity/tags 또는 복호문자열에 포함되는 항목만 반환.
    """
    where: dict = {
        "ownerUserId": user_id,
        "visibility": KnowledgeVisibility.PRIVATE.value,
    }
    rows = await prisma.knowledgefact.find_many(
        where=where, order={"createdAt": "desc"}, take=500
    )

    out: list[KnowledgeFact] = []
    q = (query or "").strip().lower()
    for r in rows:
        try:
            plain = decrypt_for_user(r.content, user_id, master_key)
        except Exception as exc:
            logger.warning("decrypt failed for %s: %s", r.id, exc)
            continue
        if q:
            blob = " ".join(
                [plain, r.domain or "", r.entity or "", " ".join(r.tags or [])]
            ).lower()
            if q not in blob:
                continue
        out.append(
            KnowledgeFact(
                id=r.id,
                content=plain,
                domain=r.domain,
                entity=r.entity,
                tags=list(r.tags or []),
                language=r.language,
                valid_from=r.validFrom,
                valid_to=r.validTo,
                created_at=r.createdAt,
                last_verified_at=r.lastVerifiedAt,
                confidence_t0=float(r.confidenceT0 or 1.0),
                half_life_days=r.halfLifeDays,
                status=r.status,
                source=r.source,
                source_url=r.sourceUrl,
                source_type=r.sourceType,
                visibility=KnowledgeVisibility.PRIVATE,
                owner_user_id=r.ownerUserId,
            )
        )
    await audit_access(user_id, "*", f"load_private(n={len(out)})")
    return out


# ─────────────────────────────────────────────
# Differential Privacy
# ─────────────────────────────────────────────
def add_dp_noise(value: float, epsilon: float = 1.0, sensitivity: float = 1.0) -> float:
    """Laplace 메커니즘으로 DP 노이즈 추가.

    scale = sensitivity / epsilon. epsilon 이 너무 작으면 scale 폭주 → cap.
    """
    eps = max(1e-6, float(epsilon))
    scale = float(sensitivity) / eps
    # inverse CDF 방식 Laplace 샘플링
    u = random.random() - 0.5
    # sign(u) * scale * ln(1 - 2|u|)
    noise = -scale * math.copysign(1.0, u) * math.log(1 - 2 * abs(u))
    return float(value) + noise


async def dp_aggregate_counts(domain: str, epsilon: float = 1.0) -> dict:
    """도메인 안에서 entity 별 팩트 수를 집계 + DP 노이즈.

    반환: {"domain", "epsilon", "total", "by_entity": {entity: noisy_count}}.
    음수로 나온 노이즈 결과는 0 으로 클리핑.
    """
    rows = await prisma.knowledgefact.find_many(
        where={"domain": domain, "visibility": KnowledgeVisibility.PUBLIC.value},
        take=10000,
    )
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r.entity or "(none)"] += 1

    noisy: dict[str, int] = {}
    for k, v in counts.items():
        n = add_dp_noise(float(v), epsilon=epsilon, sensitivity=1.0)
        noisy[k] = max(0, int(round(n)))
    total_noisy = max(0, int(round(add_dp_noise(float(len(rows)), epsilon=epsilon))))
    return {
        "domain": domain,
        "epsilon": epsilon,
        "total": total_noisy,
        "by_entity": noisy,
    }


# ─────────────────────────────────────────────
# PII redaction
# ─────────────────────────────────────────────
_PHONE_RE = re.compile(r"\b0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}\b")
_RRN_RE = re.compile(r"\b\d{6}[-\s]?[1-4]\d{6}\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_CARD_RE = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")


async def redact_pii(content: str) -> str:
    """한국형 PII (주민번호/전화/이메일/카드) 마스킹."""
    if not content:
        return content
    out = _RRN_RE.sub("[REDACTED-RRN]", content)
    out = _PHONE_RE.sub("[REDACTED-PHONE]", out)
    out = _CARD_RE.sub("[REDACTED-CARD]", out)
    out = _EMAIL_RE.sub("[REDACTED-EMAIL]", out)
    return out


# ─────────────────────────────────────────────
# Audit log
# ─────────────────────────────────────────────
async def audit_access(user_id: str, fact_id: str, action: str) -> None:
    """접근 감사 로그.

    Prisma 에 KnowledgeAccessLog 가 있으면 기록, 없으면 stdout 로거로 대체.
    실패해도 호출자에게 예외를 던지지 않는다.
    """
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "fact_id": fact_id,
        "action": action,
    }
    try:
        await prisma.knowledgeaccesslog.create(  # type: ignore[attr-defined]
            data={
                "userId": user_id,
                "factId": fact_id if fact_id != "*" else None,
                "action": action,
            }
        )
        return
    except Exception:
        pass
    logger.info("HLKM audit %s", entry)


__all__ = [
    "encrypt_for_user",
    "decrypt_for_user",
    "store_private_fact",
    "load_private_facts",
    "add_dp_noise",
    "dp_aggregate_counts",
    "redact_pii",
    "audit_access",
]
