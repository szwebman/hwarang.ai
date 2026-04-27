"""HLKM ⑦ - Federated Fact Check (연합 사실 확인).

여러 HLKM 인스턴스 간에 프라이버시를 유지하면서 교차 검증을 수행한다.
다른 조직 / 다른 도메인의 HLKM 이 각자의 원본 데이터는 노출하지 않고
"우리가 아는 것과 합치하는지" 만 교환할 수 있게 한다.

프로토콜 개요:
  - register_instance: 우리 DB 에 상대 인스턴스 메타 등록
  - handshake: 공개키 교환 + 서명된 challenge 검증
  - query_federated_instance: 개별 사실/엔티티를 상대에게 질의
  - cross_verify_fact: 여러 인스턴스의 응답을 종합해 신뢰도 산출
  - serve_federated_query: 우리가 상대 쿼리에 응답 (PRIVATE 은 반드시 제외)

프라이버시 원칙:
  * visibility=PRIVATE 또는 RESTRICTED 는 연합 응답에서 제외
  * ownerUserId 등 PII 는 응답 직렬화에서 제거
  * 서명 가능한 경우 Ed25519, 없으면 HMAC 폴백
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Any

from hwarang_api.db import prisma

from .audit import hash_fact, record_event
from .types import KnowledgeFact, KnowledgeStatus

logger = logging.getLogger(__name__)

try:  # pragma: no cover - 선택 의존성
    import httpx  # type: ignore

    _HAS_HTTPX = True
except Exception:
    _HAS_HTTPX = False

try:  # pragma: no cover - 선택 의존성
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # type: ignore
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives import serialization  # type: ignore

    _HAS_CRYPTO = True
except Exception:
    _HAS_CRYPTO = False


# ─────────────────────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────────────────────
_OUR_INSTANCE_ID = os.environ.get("HLKM_INSTANCE_ID", "local-hlkm")
_OUR_NAME = os.environ.get("HLKM_INSTANCE_NAME", "HWARANG-HLKM")
_OUR_VERSION = os.environ.get("HLKM_VERSION", "0.1.0")
_PRIVATE_KEY_FILE = os.environ.get(
    "HLKM_FEDERATION_KEY", "/var/hlkm/federation_private_key.pem"
)
_REQUEST_TIMEOUT = 10.0

_TRUST_FLOOR = 0.0
_TRUST_CEIL = 1.0
_TRUST_DELTA_CAP = 0.1   # 한 번에 조정 가능한 trust 폭


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clamp(x: float, lo: float = _TRUST_FLOOR, hi: float = _TRUST_CEIL) -> float:
    return max(lo, min(hi, float(x)))


# ─────────────────────────────────────────────────────────────
# 인스턴스 등록 / 조회
# ─────────────────────────────────────────────────────────────
async def register_instance(
    instance_id: str,
    name: str,
    api_url: str,
    public_key: str,
    organization: str | None = None,
    trust_level: float = 0.5,
) -> str:
    """새 연합 인스턴스를 등록한다. 이미 존재하면 메타만 업데이트."""
    data = {
        "instanceId": instance_id,
        "name": name,
        "apiUrl": api_url,
        "publicKey": public_key,
        "organization": organization,
        "trustLevel": _clamp(trust_level),
        "active": True,
        "syncsCompleted": 0,
    }
    try:
        row = await prisma.federatedinstance.upsert(  # type: ignore[attr-defined]
            where={"instanceId": instance_id},
            data={
                "create": data,
                "update": {
                    "name": name,
                    "apiUrl": api_url,
                    "publicKey": public_key,
                    "organization": organization,
                },
            },
        )
        return row.id if hasattr(row, "id") else instance_id
    except Exception as exc:
        logger.warning("register_instance failed: %s", exc)
        try:
            row = await prisma.federatedinstance.create(data=data)  # type: ignore[attr-defined]
            return row.id
        except Exception as exc2:
            logger.error("register_instance create also failed: %s", exc2)
            return ""


async def list_instances(active_only: bool = True) -> list[dict]:
    """등록된 연합 인스턴스 목록."""
    where: dict[str, Any] = {}
    if active_only:
        where["active"] = True
    try:
        rows = await prisma.federatedinstance.find_many(  # type: ignore[attr-defined]
            where=where, take=500,
        )
    except Exception as exc:
        logger.warning("list_instances failed: %s", exc)
        return []
    out: list[dict] = []
    for r in rows:
        out.append({
            "instance_id": r.instanceId,
            "name": r.name,
            "api_url": r.apiUrl,
            "organization": r.organization,
            "trust_level": float(r.trustLevel or 0.0),
            "active": bool(r.active),
            "last_handshake_at": r.lastHandshakeAt.isoformat() if r.lastHandshakeAt else None,
            "syncs_completed": int(r.syncsCompleted or 0),
        })
    return out


# ─────────────────────────────────────────────────────────────
# 키 / 서명
# ─────────────────────────────────────────────────────────────
def generate_keypair() -> tuple[str, str]:
    """Ed25519 (선택) 혹은 HMAC 폴백용 대칭키를 생성.

    반환 (public_key, private_key) — 모두 base64.

    주의: 한 번만 호출하고 환경변수/파일에 안전하게 저장해야 한다.
    """
    if _HAS_CRYPTO:
        sk = Ed25519PrivateKey.generate()
        pk = sk.public_key()
        sk_bytes = sk.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        pk_bytes = pk.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return (
            base64.b64encode(pk_bytes).decode("ascii"),
            base64.b64encode(sk_bytes).decode("ascii"),
        )
    # HMAC 폴백: 같은 32바이트 키를 public/private 쌍처럼 반환 (대칭)
    key = secrets.token_bytes(32)
    encoded = base64.b64encode(key).decode("ascii")
    return encoded, encoded


def _sign(payload: str, private_key_b64: str) -> str:
    """payload 에 대한 서명을 base64 문자열로 생성."""
    try:
        sk_bytes = base64.b64decode(private_key_b64)
    except Exception:
        sk_bytes = private_key_b64.encode("utf-8")

    if _HAS_CRYPTO and len(sk_bytes) == 32:
        try:
            sk = Ed25519PrivateKey.from_private_bytes(sk_bytes)
            sig = sk.sign(payload.encode("utf-8"))
            return base64.b64encode(sig).decode("ascii")
        except Exception:
            pass
    mac = hmac.new(sk_bytes, payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(mac).decode("ascii")


async def verify_signature(payload: str, signature: str, public_key: str) -> bool:
    """상대 서명 검증. Ed25519 우선, 실패 시 HMAC 폴백."""
    try:
        sig_bytes = base64.b64decode(signature)
    except Exception:
        return False
    try:
        pk_bytes = base64.b64decode(public_key)
    except Exception:
        pk_bytes = public_key.encode("utf-8")

    if _HAS_CRYPTO and len(pk_bytes) == 32 and len(sig_bytes) == 64:
        try:
            pk = Ed25519PublicKey.from_public_bytes(pk_bytes)
            pk.verify(sig_bytes, payload.encode("utf-8"))
            return True
        except Exception:
            return False
    # HMAC 검증 (대칭키)
    try:
        expected = hmac.new(pk_bytes, payload.encode("utf-8"), hashlib.sha256).digest()
        return hmac.compare_digest(expected, sig_bytes)
    except Exception:
        return False


def _load_our_private_key() -> str | None:
    try:
        if os.path.exists(_PRIVATE_KEY_FILE):
            with open(_PRIVATE_KEY_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception as exc:
        logger.debug("private key read failed: %s", exc)
    return os.environ.get("HLKM_FEDERATION_PRIVATE_KEY")


# ─────────────────────────────────────────────────────────────
# HTTP 호출
# ─────────────────────────────────────────────────────────────
async def _post(url: str, payload: dict) -> dict:
    """상대 인스턴스에 POST. httpx 없으면 폴백으로 빈 결과 반환."""
    if not _HAS_HTTPX:
        logger.warning("httpx not installed — federated HTTP disabled")
        return {"error": "httpx_missing"}
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:  # type: ignore
            r = await client.post(url, json=payload)
            if r.status_code >= 400:
                return {"error": f"http_{r.status_code}", "body": r.text}
            return r.json() if r.content else {}
    except Exception as exc:
        logger.warning("federated POST %s failed: %s", url, exc)
        return {"error": f"exception:{exc}"}


# ─────────────────────────────────────────────────────────────
# 핸드셰이크
# ─────────────────────────────────────────────────────────────
async def handshake(instance_id: str) -> dict:
    """상대 인스턴스에 핸드셰이크 요청. 서명 검증 + lastHandshakeAt 업데이트."""
    try:
        row = await prisma.federatedinstance.find_unique(  # type: ignore[attr-defined]
            where={"instanceId": instance_id}
        )
    except Exception as exc:
        logger.warning("handshake lookup failed: %s", exc)
        return {"ok": False, "error": "lookup_failed"}
    if row is None:
        return {"ok": False, "error": "unknown_instance"}

    challenge = secrets.token_hex(16)
    priv = _load_our_private_key()
    payload = {
        "our_id": _OUR_INSTANCE_ID,
        "our_name": _OUR_NAME,
        "version": _OUR_VERSION,
        "challenge": challenge,
        "issued_at": _utcnow().isoformat(),
    }
    body_str = json.dumps(payload, sort_keys=True)
    signature = _sign(body_str, priv) if priv else ""

    resp = await _post(
        f"{row.apiUrl.rstrip('/')}/api/federated/handshake",
        {"payload": payload, "signature": signature},
    )

    ok = False
    their_version = resp.get("version")
    # 상대가 our challenge 에 서명해 응답했는지 검증
    their_sig = resp.get("challenge_signature") or resp.get("signature")
    if their_sig and row.publicKey:
        try:
            ok = await verify_signature(challenge, their_sig, row.publicKey)
        except Exception as exc:
            logger.warning("handshake signature verify failed: %s", exc)
            ok = False

    if ok:
        try:
            await prisma.federatedinstance.update(  # type: ignore[attr-defined]
                where={"instanceId": instance_id},
                data={"lastHandshakeAt": _utcnow()},
            )
        except Exception as exc:
            logger.debug("handshake persist failed: %s", exc)

    return {
        "ok": ok,
        "their_version": their_version,
        "trust_level": float(row.trustLevel or 0.0),
        "instance_id": instance_id,
        "raw_response": resp,
    }


# ─────────────────────────────────────────────────────────────
# 개별 질의
# ─────────────────────────────────────────────────────────────
def _sanitize_for_export(row: Any) -> dict:
    """PRIVATE/RESTRICTED 제외 + PII 삭제 후 dict 로 반환."""
    if row is None:
        return {}
    d: dict[str, Any] = {}
    if hasattr(row, "model_dump"):
        try:
            d = row.model_dump()
        except Exception:
            d = {}
    if not d:
        for k in ("id", "content", "contentHash", "domain", "entity", "status",
                  "validFrom", "validTo", "confidenceT0", "source", "sourceUrl",
                  "visibility"):
            if hasattr(row, k):
                v = getattr(row, k)
                d[k] = v.isoformat() if isinstance(v, datetime) else v
    vis = str(d.get("visibility") or "PUBLIC").upper()
    if vis in {"PRIVATE", "RESTRICTED"}:
        return {}
    d.pop("ownerUserId", None)
    d.pop("contributedBy", None)
    return d


def _text_similarity(a: str, b: str) -> float:
    """간단한 Jaccard 기반 텍스트 유사도 (의존성 없이)."""
    if not a or not b:
        return 0.0
    ta = set(a.lower().split())
    tb = set(b.lower().split())
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


async def query_federated_instance(
    instance_id: str,
    fact_id: str | None = None,
    entity: str | None = None,
    query_text: str | None = None,
) -> dict:
    """상대 인스턴스에 질의하고 응답의 agreement 를 계산한다.

    FederatedQuery 레코드를 남겨 통신 이력을 감사한다.
    """
    if not any([fact_id, entity, query_text]):
        raise ValueError("at least one of fact_id / entity / query_text required")

    try:
        inst = await prisma.federatedinstance.find_unique(  # type: ignore[attr-defined]
            where={"instanceId": instance_id}
        )
    except Exception as exc:
        logger.warning("query lookup failed: %s", exc)
        return {"error": "lookup_failed"}
    if inst is None:
        return {"error": "unknown_instance"}

    sent_at = _utcnow()
    query_payload: dict[str, Any] = {
        "our_id": _OUR_INSTANCE_ID,
        "fact_id": fact_id,
        "entity": entity,
        "query": query_text,
        "sent_at": sent_at.isoformat(),
    }

    # 로컬 기준 원본 가져와 비교
    our_fact: dict = {}
    if fact_id:
        try:
            own = await prisma.knowledgefact.find_unique(where={"id": fact_id})
            our_fact = _sanitize_for_export(own)
        except Exception:
            our_fact = {}

    resp = await _post(
        f"{inst.apiUrl.rstrip('/')}/api/federated/query",
        query_payload,
    )
    received_at = _utcnow()

    # agreement 계산
    agreement = _compute_agreement(our_fact, resp, entity=entity)
    verdict = _agreement_verdict(agreement)

    try:
        await prisma.federatedquery.create(  # type: ignore[attr-defined]
            data={
                "instanceId": instance_id,
                "factId": fact_id,
                "entity": entity,
                "query": query_text or "",
                "sentAt": sent_at,
                "receivedAt": received_at,
                "response": resp,
                "agreement": float(agreement),
                "status": "ok" if "error" not in resp else "error",
            }
        )
    except Exception as exc:
        logger.debug("FederatedQuery persist failed: %s", exc)

    return {
        "instance_id": instance_id,
        "agreement": agreement,
        "verdict": verdict,
        "remote_response": resp,
        "our_fact": our_fact,
        "round_trip_ms": int((received_at - sent_at).total_seconds() * 1000),
    }


def _compute_agreement(our_fact: dict, resp: dict, entity: str | None) -> float:
    """fact 또는 entity 기준으로 0~1 agreement 를 계산."""
    if not resp or "error" in resp:
        return 0.0
    # fact 기준: 상대가 같은 사실을 가지고 있는지 + validTo 일치 + 내용 유사도
    if our_fact and our_fact.get("id"):
        their = resp.get("fact") or {}
        if not their:
            return 0.0
        score = 0.0
        # valid_to 일치
        ours_vt = str(our_fact.get("validTo") or "")
        theirs_vt = str(their.get("validTo") or "")
        if ours_vt == theirs_vt:
            score += 0.25
        # status
        if str(our_fact.get("status")) == str(their.get("status")):
            score += 0.2
        # 내용 유사도
        sim = _text_similarity(
            str(our_fact.get("content") or ""),
            str(their.get("content") or ""),
        )
        score += 0.55 * sim
        return _clamp(score, 0.0, 1.0)
    # entity 기준: 교집합 / 합집합 (id 기반)
    if entity:
        their_facts = resp.get("facts") or []
        if not isinstance(their_facts, list) or not their_facts:
            return 0.0
        their_ids = {str(f.get("id")) for f in their_facts if f.get("id")}
        # 우리 쪽 같은 entity fact ids 는 호출측이 제공하지 않으므로 크기 비교로 근사
        size_score = min(1.0, len(their_ids) / 10.0)
        return _clamp(size_score, 0.0, 1.0)
    # 일반 query: 상대가 결과를 반환했으면 0.5
    if resp.get("facts") or resp.get("result"):
        return 0.5
    return 0.0


def _agreement_verdict(agreement: float) -> str:
    if agreement >= 0.8:
        return "strong_agree"
    if agreement >= 0.5:
        return "agree"
    if agreement >= 0.2:
        return "weak_agree"
    return "disagree"


# ─────────────────────────────────────────────────────────────
# 교차 검증
# ─────────────────────────────────────────────────────────────
async def cross_verify_fact(fact_id: str, min_instances: int = 2) -> dict:
    """우리 쪽 fact_id 를 여러 연합 인스턴스에 조회하여 종합 판정."""
    instances = await list_instances(active_only=True)
    if len(instances) < min_instances:
        return {
            "verified": False,
            "error": "insufficient_instances",
            "available": len(instances),
            "required": min_instances,
        }

    confirming: list[dict] = []
    dissenting: list[dict] = []
    scores: list[float] = []

    for inst in instances:
        result = await query_federated_instance(inst["instance_id"], fact_id=fact_id)
        if "error" in result:
            continue
        agreement = float(result.get("agreement", 0.0))
        scores.append(agreement)
        entry = {
            "instance_id": inst["instance_id"],
            "name": inst.get("name"),
            "agreement": agreement,
            "trust_level": inst.get("trust_level", 0.0),
        }
        if agreement >= 0.5:
            confirming.append(entry)
        else:
            dissenting.append(entry)

    if not scores:
        return {"verified": False, "error": "no_response"}

    # trust-weighted average
    weighted = 0.0
    weight_sum = 0.0
    for inst, s in zip(instances[: len(scores)], scores):
        w = max(0.1, float(inst.get("trust_level", 0.5)))
        weighted += s * w
        weight_sum += w
    agreement_avg = (weighted / weight_sum) if weight_sum else (sum(scores) / len(scores))

    verified = (
        agreement_avg >= 0.6
        and len(confirming) >= min_instances
        and len(confirming) >= len(dissenting)
    )

    return {
        "verified": verified,
        "agreement_avg": round(agreement_avg, 4),
        "confirming_instances": confirming,
        "dissenting_instances": dissenting,
        "sample_size": len(scores),
    }


# ─────────────────────────────────────────────────────────────
# 서빙
# ─────────────────────────────────────────────────────────────
async def serve_federated_query(
    remote_instance_id: str, query_payload: dict
) -> dict:
    """다른 인스턴스가 우리에게 쿼리했을 때의 응답 생성.

    visibility=PRIVATE / RESTRICTED 는 반드시 제외하며, 가능한 한 적은
    정보만 돌려준다 (공개 사실만). 모든 응답은 audit 로 남긴다.
    """
    fact_id = query_payload.get("fact_id")
    entity = query_payload.get("entity")
    query_text = query_payload.get("query")

    out: dict[str, Any] = {
        "served_by": _OUR_INSTANCE_ID,
        "received_at": _utcnow().isoformat(),
    }

    try:
        if fact_id:
            row = await prisma.knowledgefact.find_unique(where={"id": fact_id})
            sanitized = _sanitize_for_export(row)
            if sanitized:
                # content hash 만 반환하여 정보 유출을 최소화 가능, 여기서는 full 공개 필드만
                out["fact"] = {
                    k: sanitized.get(k)
                    for k in ("id", "content", "contentHash", "domain", "entity",
                              "status", "validFrom", "validTo", "source")
                }
            else:
                out["fact"] = None
        elif entity:
            rows = await prisma.knowledgefact.find_many(
                where={
                    "entity": entity,
                    "visibility": "PUBLIC",
                },
                take=50,
            )
            out["facts"] = [
                {
                    k: s.get(k)
                    for k in ("id", "content", "domain", "status", "validFrom", "validTo")
                }
                for s in (_sanitize_for_export(r) for r in rows)
                if s
            ]
        elif query_text:
            # 간단한 텍스트 포함 검색만 제공
            rows = await prisma.knowledgefact.find_many(
                where={"visibility": "PUBLIC", "content": {"contains": query_text}},
                take=20,
            )
            out["facts"] = [
                {k: s.get(k) for k in ("id", "content", "entity", "status")}
                for s in (_sanitize_for_export(r) for r in rows)
                if s
            ]
        else:
            out["error"] = "no_query_parameters"
    except Exception as exc:
        logger.warning("serve_federated_query DB error: %s", exc)
        out["error"] = f"db_error:{exc}"

    # 감사 기록
    try:
        await record_event(
            event_type="federated.serve",
            target_id=str(fact_id or entity or "query"),
            actor_id=remote_instance_id,
            before=None,
            after={"query": query_payload},
            metadata={"response_keys": list(out.keys())},
        )
    except Exception as exc:
        logger.debug("federated.serve audit skipped: %s", exc)

    return out


# ─────────────────────────────────────────────────────────────
# 연합 합의
# ─────────────────────────────────────────────────────────────
async def aggregate_consensus_across_federation(entity: str) -> dict:
    """동일 entity 에 대한 여러 인스턴스의 사실을 통합하여 합의 강도 계산."""
    instances = await list_instances(active_only=True)
    if not instances:
        return {"entity": entity, "consensus_strength": 0.0, "instance_count": 0}

    per_instance: list[dict] = []
    all_contents: list[tuple[str, str]] = []   # (instance_id, content_hash)

    for inst in instances:
        resp = await query_federated_instance(inst["instance_id"], entity=entity)
        if "error" in resp:
            continue
        remote = resp.get("remote_response", {})
        facts = remote.get("facts") or []
        hashes: list[str] = []
        for f in facts:
            ch = f.get("contentHash") or hashlib.sha256(
                str(f.get("content") or "").encode("utf-8")
            ).hexdigest()
            hashes.append(ch)
            all_contents.append((inst["instance_id"], ch))
        per_instance.append({
            "instance_id": inst["instance_id"],
            "name": inst.get("name"),
            "fact_count": len(facts),
            "hash_fingerprint": hashes[:5],
        })

    # 독립 인스턴스 수만큼 같은 contentHash 가 등장하면 합의 강화
    from collections import Counter

    hash_counts = Counter(h for _, h in all_contents)
    if hash_counts:
        max_support = max(hash_counts.values())
        consensus_strength = _clamp(max_support / max(1, len(per_instance)))
    else:
        consensus_strength = 0.0

    return {
        "entity": entity,
        "instance_count": len(per_instance),
        "per_instance": per_instance,
        "consensus_strength": round(consensus_strength, 4),
        "top_claim_support": hash_counts.most_common(3),
    }


async def detect_divergent_instances(fact_id: str) -> list[dict]:
    """같은 fact 에 대해 크게 다른 입장의 인스턴스들을 조사 대상으로 반환."""
    instances = await list_instances(active_only=True)
    divergent: list[dict] = []
    for inst in instances:
        result = await query_federated_instance(inst["instance_id"], fact_id=fact_id)
        if "error" in result:
            continue
        if result.get("agreement", 1.0) < 0.3:
            divergent.append({
                "instance_id": inst["instance_id"],
                "name": inst.get("name"),
                "agreement": result.get("agreement"),
                "verdict": result.get("verdict"),
                "flagged_for_review": True,
            })
    return divergent


# ─────────────────────────────────────────────────────────────
# 신뢰 레벨 조정
# ─────────────────────────────────────────────────────────────
async def update_trust_level(
    instance_id: str, delta: float, reason: str
) -> float:
    """상호작용 결과에 따라 인스턴스의 trustLevel 을 동적 조정.

    delta 는 ±_TRUST_DELTA_CAP 로 자동 클램프된다.
    """
    clamped_delta = max(-_TRUST_DELTA_CAP, min(_TRUST_DELTA_CAP, float(delta)))
    try:
        row = await prisma.federatedinstance.find_unique(  # type: ignore[attr-defined]
            where={"instanceId": instance_id}
        )
    except Exception:
        row = None
    if row is None:
        return 0.0
    old = float(row.trustLevel or 0.5)
    new = _clamp(old + clamped_delta)

    try:
        await prisma.federatedinstance.update(  # type: ignore[attr-defined]
            where={"instanceId": instance_id},
            data={"trustLevel": new},
        )
    except Exception as exc:
        logger.warning("update_trust_level persist failed: %s", exc)
        return old

    try:
        await record_event(
            event_type="federated.trust_update",
            target_id=instance_id,
            actor_id=_OUR_INSTANCE_ID,
            before={"trust_level": old},
            after={"trust_level": new},
            metadata={"delta": clamped_delta, "reason": reason},
        )
    except Exception as exc:
        logger.debug("trust audit skipped: %s", exc)

    return new


__all__ = [
    "register_instance",
    "list_instances",
    "handshake",
    "query_federated_instance",
    "cross_verify_fact",
    "verify_signature",
    "generate_keypair",
    "serve_federated_query",
    "aggregate_consensus_across_federation",
    "detect_divergent_instances",
    "update_trust_level",
]
