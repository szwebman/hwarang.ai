"""HLKM - Sybil 방어 (가짜 계정 자동 탐지).

IP / 디바이스 / 행동 패턴 분석으로 다중 계정/봇/공모 그룹을
자동 감지하여 `SybilFlag` 레코드로 기록한다.

탐지 룰:
  1. `detect_ip_cluster`           — 같은 IP에서 다수 계정이 활동
  2. `detect_behavioral_similarity`— 제출 시간대/문체/도메인 시그니처 유사
  3. `detect_temporal_burst`       — 단시간 대량 기여 (봇 의심)
  4. `detect_mutual_voting_ring`   — 상호-accept 만 하는 공모 그룹

의존:
  - `hwarang_api.db.prisma` (Prisma 클라이언트)
  - 내부 모듈만 사용 (외부 네트워크 호출 없음)

프라이버시:
  - 실제 IP 는 `_ip_fingerprint` 로 salt+SHA256 해시만 저장한다.
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma

from .types import KnowledgeFact  # noqa: F401  (공개 API 타입 안정화)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────
_IP_SALT = os.getenv("HWARANG_SYBIL_IP_SALT", "hwarang-sybil-v1")
_SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}

# 기여 제출 시간대(24구간) 분포가 이 임계 이상 유사하면 봇 의심
_BEHAVIOR_SIM_THRESHOLD = 0.9
_VOTING_RING_JACCARD = 0.7
_IP_CLUSTER_THRESHOLD = 3
_DEFAULT_BURST_THRESHOLD = 20


# ─────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ip_fingerprint(ip: str, user_agent: str) -> str:
    """IP + UA prefix 를 salt+SHA256 해시한 fingerprint.

    - UA 는 앞 32자만 사용 (버전 세밀 차이 무시).
    - 프라이버시 보호를 위해 원본 IP 는 저장하지 않는다.
    """
    ua_prefix = (user_agent or "")[:32]
    payload = f"{_IP_SALT}|{ip or ''}|{ua_prefix}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


def _behavioral_signature(contribs: list[dict]) -> str:
    """기여 패턴으로 24차원 시간대 + Top5 도메인 fingerprint 생성."""
    hour_buckets: list[int] = [0] * 24
    domain_counter: Counter[str] = Counter()

    for c in contribs:
        ts = c.get("created_at") or c.get("acceptedAt")
        if isinstance(ts, datetime):
            hour_buckets[ts.hour] += 1
        domain = (c.get("domain") or "").lower()
        if domain:
            domain_counter[domain] += 1

    total = sum(hour_buckets) or 1
    hour_dist = "-".join(f"{(v / total):.2f}" for v in hour_buckets)
    top_domains = ",".join(d for d, _ in domain_counter.most_common(5))
    return hashlib.sha256(f"{hour_dist}|{top_domains}".encode()).hexdigest()[:24]


def _cosine_distribution(a: list[float], b: list[float]) -> float:
    """두 시간대 분포 코사인 유사도(0~1)."""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def _hour_distribution(contribs: list[dict]) -> list[float]:
    buckets = [0] * 24
    for c in contribs:
        ts = c.get("created_at") or c.get("acceptedAt")
        if isinstance(ts, datetime):
            buckets[ts.hour] += 1
    total = sum(buckets) or 1
    return [v / total for v in buckets]


async def _recent_contributions(user_id: str, days: int = 30) -> list[dict]:
    """해당 사용자의 최근 기여 목록 (KnowledgeContribution)."""
    since = _utcnow() - timedelta(days=days)
    rows = await prisma.knowledgecontribution.find_many(
        where={"contributorId": user_id, "acceptedAt": {"gte": since}},
        take=1000,
        order={"acceptedAt": "desc"},
    )
    out: list[dict] = []
    for r in rows:
        fact = await prisma.knowledgefact.find_unique(where={"id": r.factId})
        out.append(
            {
                "fact_id": r.factId,
                "created_at": r.acceptedAt,
                "acceptedAt": r.acceptedAt,
                "domain": (fact.domain if fact else None),
                "content": (fact.content if fact else ""),
            }
        )
    return out


# ─────────────────────────────────────────────
# 개별 탐지 룰
# ─────────────────────────────────────────────
async def detect_ip_cluster(user_id: str, window_days: int = 30) -> dict | None:
    """같은 IP fingerprint 에서 다수 계정이 활동하는지 감지.

    - `UserSession` 테이블이 있으면 그것을 사용.
    - 없으면 `ContributorProfile.lastActiveAt` 기반 근사치 사용.
    """
    since = _utcnow() - timedelta(days=window_days)

    related_ids: list[str] = []
    fingerprint: str | None = None

    try:
        sessions = await prisma.usersession.find_many(  # type: ignore[attr-defined]
            where={"userId": user_id, "createdAt": {"gte": since}},
            take=200,
        )
        if not sessions:
            return None
        fp = _ip_fingerprint(
            getattr(sessions[0], "ipAddress", "") or "",
            getattr(sessions[0], "userAgent", "") or "",
        )
        fingerprint = fp
        peers = await prisma.usersession.find_many(  # type: ignore[attr-defined]
            where={"ipFingerprint": fp, "createdAt": {"gte": since}},
            take=500,
        )
        related_ids = sorted({s.userId for s in peers if s.userId != user_id})
    except Exception as exc:
        logger.debug("usersession unavailable, using approximate cluster: %s", exc)
        profile = await prisma.contributorprofile.find_unique(where={"userId": user_id})
        if profile is None or profile.lastActiveAt is None:
            return None
        window_start = profile.lastActiveAt - timedelta(minutes=5)
        window_end = profile.lastActiveAt + timedelta(minutes=5)
        peers = await prisma.contributorprofile.find_many(
            where={
                "lastActiveAt": {"gte": window_start, "lte": window_end},
                "userId": {"not": user_id},
            },
            take=100,
        )
        related_ids = [p.userId for p in peers]

    if len(related_ids) < _IP_CLUSTER_THRESHOLD - 1:
        return None

    severity = "high" if len(related_ids) >= 5 else "medium"
    return {
        "pattern": "ip_cluster",
        "severity": severity,
        "evidence": {
            "fingerprint": fingerprint,
            "cluster_size": len(related_ids) + 1,
            "window_days": window_days,
        },
        "related_user_ids": related_ids,
    }


async def detect_behavioral_similarity(user_id: str) -> dict | None:
    """기여 패턴(시간대 분포 + 도메인 선호)으로 유사 계정 감지.

    코사인 유사도 > `_BEHAVIOR_SIM_THRESHOLD` 인 다른 사용자 flag.
    """
    contribs = await _recent_contributions(user_id)
    if len(contribs) < 5:
        return None
    target_dist = _hour_distribution(contribs)
    target_domains = Counter(
        (c.get("domain") or "").lower() for c in contribs if c.get("domain")
    )

    others = await prisma.contributorprofile.find_many(
        where={"userId": {"not": user_id}}, take=500
    )
    similar: list[tuple[str, float]] = []
    for prof in others:
        peer_contribs = await _recent_contributions(prof.userId)
        if len(peer_contribs) < 5:
            continue
        peer_dist = _hour_distribution(peer_contribs)
        sim_time = _cosine_distribution(target_dist, peer_dist)

        peer_domains = Counter(
            (c.get("domain") or "").lower()
            for c in peer_contribs
            if c.get("domain")
        )
        shared = set(target_domains) & set(peer_domains)
        union = set(target_domains) | set(peer_domains)
        sim_dom = (len(shared) / len(union)) if union else 0.0

        sim = 0.6 * sim_time + 0.4 * sim_dom
        if sim >= _BEHAVIOR_SIM_THRESHOLD:
            similar.append((prof.userId, sim))

    if not similar:
        return None
    similar.sort(key=lambda x: x[1], reverse=True)
    top = similar[:10]
    return {
        "pattern": "behavioral_similarity",
        "severity": "high" if top[0][1] > 0.95 else "medium",
        "evidence": {
            "signature": _behavioral_signature(contribs),
            "top_similar": [{"user_id": u, "similarity": round(s, 3)} for u, s in top],
        },
        "related_user_ids": [u for u, _ in top],
    }


async def detect_temporal_burst(
    user_id: str,
    window_hours: int = 1,
    threshold: int = _DEFAULT_BURST_THRESHOLD,
) -> dict | None:
    """단시간 대량 기여(봇 의심)."""
    contribs = await _recent_contributions(user_id, days=7)
    if len(contribs) < threshold:
        return None

    # 슬라이딩 윈도우 최대 카운트
    timestamps = sorted(
        c["created_at"] for c in contribs if isinstance(c.get("created_at"), datetime)
    )
    if len(timestamps) < threshold:
        return None

    window = timedelta(hours=window_hours)
    max_count = 0
    peak_start: datetime | None = None
    left = 0
    for right, ts in enumerate(timestamps):
        while timestamps[right] - timestamps[left] > window:
            left += 1
        count = right - left + 1
        if count > max_count:
            max_count = count
            peak_start = timestamps[left]

    if max_count < threshold:
        return None
    severity = "critical" if max_count > threshold * 2 else "high"
    return {
        "pattern": "temporal_burst",
        "severity": severity,
        "evidence": {
            "window_hours": window_hours,
            "max_count": max_count,
            "threshold": threshold,
            "peak_start": peak_start.isoformat() if peak_start else None,
        },
        "related_user_ids": [],
    }


async def detect_mutual_voting_ring(user_ids: list[str]) -> dict | None:
    """N명 그룹이 서로만 accept 하는 공모 패턴 (Jaccard > 0.7).

    `KnowledgeContribution` 의 votesUp 이 peer review accept 을 대리한다.
    """
    if len(user_ids) < 2:
        return None

    # 각 user 가 "지지한" 대상(기여자) 집합
    supported: dict[str, set[str]] = {}
    for uid in user_ids:
        rows = await prisma.knowledgecontribution.find_many(
            where={"contributorId": {"in": [u for u in user_ids if u != uid]}},
            take=500,
        )
        # 발견된 대상 기여자를 지지로 간주 (실제 upvote 테이블이 있다면 교체)
        supported[uid] = {r.contributorId for r in rows if (r.votesUp or 0) > 0}

    # 링 내부 Jaccard 평균
    members = list(user_ids)
    scores: list[float] = []
    for i, a in enumerate(members):
        for b in members[i + 1 :]:
            sa, sb = supported.get(a, set()), supported.get(b, set())
            if not sa and not sb:
                continue
            union = sa | sb
            if not union:
                continue
            j = len(sa & sb) / len(union)
            scores.append(j)
    if not scores:
        return None
    avg = sum(scores) / len(scores)
    if avg < _VOTING_RING_JACCARD:
        return None
    return {
        "pattern": "mutual_voting_ring",
        "severity": "critical" if avg > 0.9 else "high",
        "evidence": {
            "members": members,
            "avg_jaccard": round(avg, 3),
            "pairs_examined": len(scores),
        },
        "related_user_ids": members,
    }


# ─────────────────────────────────────────────
# 스캔/플래그 저장
# ─────────────────────────────────────────────
async def _persist_flag(user_id: str, flag: dict) -> str:
    """탐지 결과를 SybilFlag 테이블에 upsert (pattern+user 기준 중복 방지)."""
    existing = await prisma.sybilflag.find_first(
        where={
            "userId": user_id,
            "pattern": flag["pattern"],
            "resolved": False,
        }
    )
    data: dict[str, Any] = {
        "userId": user_id,
        "pattern": flag["pattern"],
        "severity": flag["severity"],
        "detectedAt": _utcnow(),
        "evidence": flag.get("evidence", {}),
        "relatedUserIds": flag.get("related_user_ids", []),
        "resolved": False,
    }
    if existing is None:
        row = await prisma.sybilflag.create(data=data)
        return row.id
    row = await prisma.sybilflag.update(
        where={"id": existing.id},
        data={
            "severity": flag["severity"],
            "detectedAt": _utcnow(),
            "evidence": flag.get("evidence", {}),
            "relatedUserIds": flag.get("related_user_ids", []),
        },
    )
    return row.id


async def scan_user(user_id: str) -> list[dict]:
    """해당 사용자에 대해 모든 탐지 룰을 실행하고 SybilFlag 생성.

    반환: 저장된 flag 메타데이터 리스트.
    """
    detected: list[dict] = []

    ip = await detect_ip_cluster(user_id)
    if ip:
        detected.append(ip)

    behavior = await detect_behavioral_similarity(user_id)
    if behavior:
        detected.append(behavior)

    burst = await detect_temporal_burst(user_id)
    if burst:
        detected.append(burst)

    saved: list[dict] = []
    for flag in detected:
        flag_id = await _persist_flag(user_id, flag)
        saved.append({**flag, "flag_id": flag_id})

    logger.info(
        "scan_user %s: %d new flags (%s)",
        user_id,
        len(saved),
        ",".join(f["pattern"] for f in saved),
    )
    return saved


async def list_active_flags(
    severity: str | None = None,
    resolved: bool = False,
    limit: int = 50,
) -> list[dict]:
    """열려있는(or 해결된) SybilFlag 목록."""
    where: dict[str, Any] = {"resolved": resolved}
    if severity:
        where["severity"] = severity
    rows = await prisma.sybilflag.find_many(
        where=where, take=limit, order={"detectedAt": "desc"}
    )
    return [
        {
            "flag_id": r.id,
            "user_id": r.userId,
            "pattern": r.pattern,
            "severity": r.severity,
            "detected_at": r.detectedAt,
            "evidence": r.evidence,
            "related_user_ids": list(r.relatedUserIds or []),
            "resolved": r.resolved,
            "resolution": r.resolution,
        }
        for r in rows
    ]


async def resolve_flag(
    flag_id: str,
    resolver_id: str,
    resolution: str,
    note: str | None = None,
) -> None:
    """플래그 해결: 'confirmed_sybil'/'false_positive'/'warning_issued'."""
    flag = await prisma.sybilflag.find_unique(where={"id": flag_id})
    if flag is None:
        raise ValueError(f"flag not found: {flag_id}")

    evidence = dict(flag.evidence or {})
    if note:
        evidence["resolve_note"] = note

    await prisma.sybilflag.update(
        where={"id": flag_id},
        data={
            "resolved": True,
            "resolvedAt": _utcnow(),
            "resolvedBy": resolver_id,
            "resolution": resolution,
            "evidence": evidence,
        },
    )

    if resolution == "confirmed_sybil":
        await suspend_account(flag.userId, reason=f"sybil:{flag.pattern}")
    elif resolution == "warning_issued":
        logger.info("warning issued to %s for %s", flag.userId, flag.pattern)
    logger.info("flag %s resolved: %s (by %s)", flag_id, resolution, resolver_id)


async def suspend_account(
    user_id: str, reason: str, duration_days: int | None = None
) -> None:
    """계정 정지: tier=SUSPENDED, 사유/기간 저장."""
    until = (
        _utcnow() + timedelta(days=duration_days) if duration_days else None
    )
    await prisma.contributorprofile.upsert(
        where={"userId": user_id},
        data={
            "create": {
                "userId": user_id,
                "tier": "SUSPENDED",
                "suspensionReason": reason[:480],
                "suspendedUntil": until,
            },
            "update": {
                "tier": "SUSPENDED",
                "suspensionReason": reason[:480],
                "suspendedUntil": until,
            },
        },
    )
    logger.warning("account suspended: %s (%s, until=%s)", user_id, reason, until)


async def lift_suspension(user_id: str, admin_id: str) -> None:
    """정지 해제. tier 를 BRONZE 로 복원."""
    await prisma.contributorprofile.update(
        where={"userId": user_id},
        data={
            "tier": "BRONZE",
            "suspensionReason": None,
            "suspendedUntil": None,
        },
    )
    logger.info("suspension lifted: %s (by %s)", user_id, admin_id)


# ─────────────────────────────────────────────
# 클러스터 개요
# ─────────────────────────────────────────────
async def cluster_overview() -> list[dict]:
    """relatedUserIds 로 연결된 의심 클러스터 그룹 집계."""
    flags = await prisma.sybilflag.find_many(
        where={"resolved": False}, take=500
    )
    # Union-Find
    parent: dict[str, str] = {}

    def find(u: str) -> str:
        while parent.get(u, u) != u:
            parent[u] = parent.get(parent[u], parent[u])
            u = parent[u]
        return u

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for f in flags:
        parent.setdefault(f.userId, f.userId)
        for rel in f.relatedUserIds or []:
            parent.setdefault(rel, rel)
            union(f.userId, rel)

    groups: dict[str, list[str]] = defaultdict(list)
    for u in parent:
        groups[find(u)].append(u)

    out: list[dict] = []
    for root, members in groups.items():
        if len(members) < 2:
            continue
        member_flags = [f for f in flags if f.userId in members]
        max_sev = max(
            (_SEVERITY_ORDER.get(f.severity, 0) for f in member_flags),
            default=0,
        )
        sev_label = next(
            (k for k, v in _SEVERITY_ORDER.items() if v == max_sev), "low"
        )
        out.append(
            {
                "cluster_id": root,
                "members": sorted(members),
                "size": len(members),
                "flag_count": len(member_flags),
                "max_severity": sev_label,
                "patterns": sorted({f.pattern for f in member_flags}),
            }
        )
    out.sort(key=lambda g: (-g["size"], g["cluster_id"]))
    return out


# ─────────────────────────────────────────────
# 일일 배치
# ─────────────────────────────────────────────
async def daily_sybil_scan(limit: int = 500) -> dict:
    """최근 활동 계정을 샘플링하여 전체 탐지 룰 스캔.

    반환: {"scanned", "new_flags", "by_severity"}
    """
    since = _utcnow() - timedelta(days=7)
    profiles = await prisma.contributorprofile.find_many(
        where={"lastActiveAt": {"gte": since}},
        take=limit,
        order={"lastActiveAt": "desc"},
    )
    scanned = 0
    new_flags = 0
    by_severity: dict[str, int] = defaultdict(int)

    for p in profiles:
        scanned += 1
        try:
            flags = await scan_user(p.userId)
        except Exception as exc:  # noqa: BLE001
            logger.warning("scan_user failed for %s: %s", p.userId, exc)
            continue
        new_flags += len(flags)
        for f in flags:
            by_severity[f.get("severity", "low")] += 1

    logger.info(
        "daily_sybil_scan: scanned=%d new_flags=%d by_severity=%s",
        scanned,
        new_flags,
        dict(by_severity),
    )
    return {
        "scanned": scanned,
        "new_flags": new_flags,
        "by_severity": dict(by_severity),
    }


__all__ = [
    "scan_user",
    "detect_ip_cluster",
    "detect_behavioral_similarity",
    "detect_temporal_burst",
    "detect_mutual_voting_ring",
    "list_active_flags",
    "resolve_flag",
    "suspend_account",
    "lift_suspension",
    "cluster_overview",
    "daily_sybil_scan",
    "_ip_fingerprint",
    "_behavioral_signature",
]
