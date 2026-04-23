"""HLKM TAL ① — Source Hierarchy Registry.

도메인별 출처 위계 레지스트리.

"신문/블로그보다 법령/논문이 우선" 이라는 원칙을 코드로 박아둔다.
각 도메인(law/medical/politics/tech/general…)마다 여러 패턴 규칙을 두고,
출처 URL 또는 이름을 매칭해 `SourceTier` 와 `authority(0~1)` 를 결정한다.

사용 예::

    tier, authority = await lookup_authority("https://www.law.go.kr/...", "law")
    # → ("PRIMARY_OFFICIAL", 1.0)

대량 반영은 `bulk_apply_hierarchy()` 로 배치 수행.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from hwarang_api.db import prisma

# ─────────────────────────────────────────────────────────────
# 초기 시드 레지스트리
# ─────────────────────────────────────────────────────────────
#
# level 이 작을수록 상위(=우선 매칭). 같은 도메인 내에서 level 오름차순으로
# 검사하며, 최초로 매칭되는 규칙의 tier/authority 를 채택한다.
# authority 값은 해당 도메인 안에서의 "상대적" 권위이다.
DEFAULT_HIERARCHY: dict[str, list[dict[str, Any]]] = {
    "law": [
        {"level": 1, "pattern": r"law\.go\.kr", "tier": "PRIMARY_OFFICIAL", "authority": 1.0, "note": "국가법령정보센터"},
        {"level": 2, "pattern": r"scourt\.go\.kr", "tier": "PRIMARY_OFFICIAL", "authority": 0.95, "note": "대법원"},
        {"level": 3, "pattern": r"assembly\.go\.kr", "tier": "PRIMARY_OFFICIAL", "authority": 0.9, "note": "국회"},
        {"level": 4, "pattern": r"(lawtimes|legaltimes)\.co\.kr", "tier": "SPECIALIZED_MEDIA", "authority": 0.7, "note": "법률 전문 매체"},
        {"level": 5, "pattern": r"(chosun|joongang|donga|hankyoreh|khan|hani)\.com", "tier": "GENERAL_MEDIA", "authority": 0.55, "note": "주요 종합 신문"},
        {"level": 6, "pattern": r".*\.(co|or)\.kr", "tier": "GENERAL_MEDIA", "authority": 0.45, "note": "일반 국내 사이트"},
        {"level": 7, "pattern": r"(blog|cafe|tistory|brunch)", "tier": "USER_GENERATED", "authority": 0.2, "note": "블로그/커뮤니티"},
    ],
    "medical": [
        {"level": 1, "pattern": r"(pubmed\.ncbi|nature\.com|nejm\.org|thelancet\.com)", "tier": "PEER_REVIEWED", "authority": 0.98, "note": "국제 동료심사 저널"},
        {"level": 2, "pattern": r"(mohw|cdc|kdca)\.go\.kr", "tier": "PRIMARY_OFFICIAL", "authority": 0.92, "note": "보건복지부/질병청"},
        {"level": 3, "pattern": r"who\.int", "tier": "PRIMARY_OFFICIAL", "authority": 0.9, "note": "세계보건기구"},
        {"level": 4, "pattern": r"(koreamed|kci)\.go\.kr", "tier": "PEER_REVIEWED", "authority": 0.85, "note": "국내 학술 DB"},
        {"level": 5, "pattern": r"(medicaltimes|medipana)\.com", "tier": "SPECIALIZED_MEDIA", "authority": 0.65, "note": "의학 전문 매체"},
        {"level": 9, "pattern": r".*", "tier": "UNKNOWN", "authority": 0.3, "note": "의료 도메인 기본값"},
    ],
    "politics": [
        # 정치는 1차 자료도 입장 치우침 가능 → 최대 0.85로 제한.
        {"level": 1, "pattern": r"(assembly|president)\.go\.kr", "tier": "PRIMARY_OFFICIAL", "authority": 0.85, "note": "국회/대통령실"},
        {"level": 2, "pattern": r"(chosun|joongang|donga|hankyoreh|khan|hani|ohmynews|pressian)", "tier": "GENERAL_MEDIA", "authority": 0.45, "note": "정치 보도 매체"},
    ],
    "tech": [
        {"level": 1, "pattern": r"(arxiv\.org|ieee\.org|acm\.org)", "tier": "PEER_REVIEWED", "authority": 0.9, "note": "학술 프리프린트/학회"},
        {"level": 2, "pattern": r"(github\.com|developer\.mozilla\.org|stackoverflow\.com)", "tier": "SPECIALIZED_MEDIA", "authority": 0.8, "note": "1차 개발자 자료"},
        {"level": 3, "pattern": r"(techcrunch|theverge|arstechnica|zdnet)", "tier": "GENERAL_MEDIA", "authority": 0.6, "note": "기술 매체"},
    ],
    "general": [
        {"level": 9, "pattern": r".*", "tier": "UNKNOWN", "authority": 0.4, "note": "일반 도메인 기본값"},
    ],
}


# ─────────────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────────────
def extract_host(source: str) -> str:
    """URL 에서 호스트만 뽑아낸다.

    - `https://www.law.go.kr/path` → `www.law.go.kr`
    - `law.go.kr` / `조선일보` 같은 평문이면 그대로 반환.
    - 앞뒤 공백은 제거.
    """
    if not source:
        return ""
    s = source.strip()
    if "://" in s:
        try:
            parsed = urlparse(s)
            host = parsed.netloc or parsed.path
            return host.lower().strip("/")
        except Exception:
            return s.lower()
    # 스킴이 없으면 URL-like 인지 체크
    if "/" in s and "." in s.split("/", 1)[0]:
        return s.split("/", 1)[0].lower()
    return s.lower()


def _match_pattern(pattern: str, host: str, raw: str) -> bool:
    """정규식 패턴을 호스트/원문 양쪽에 매칭한다.

    일부 규칙은 경로에 `blog`, `tistory` 등을 포함하므로 raw 문자열 전체에도
    매칭을 시도한다.
    """
    if not pattern:
        return False
    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return False
    if host and compiled.search(host):
        return True
    if raw and compiled.search(raw):
        return True
    return False


# ─────────────────────────────────────────────────────────────
# 시드
# ─────────────────────────────────────────────────────────────
async def seed_default_hierarchy() -> int:
    """`DEFAULT_HIERARCHY` 를 DB 에 시드.

    이미 어떤 규칙이라도 들어있으면 건너뛴다. 반환값은 새로 삽입된 규칙 수.
    """
    try:
        existing = await prisma.sourcehierarchyrule.count()
    except Exception:
        existing = 0
    if existing:
        return 0

    inserted = 0
    for domain, rules in DEFAULT_HIERARCHY.items():
        for rule in rules:
            try:
                await prisma.sourcehierarchyrule.create(
                    data={
                        "domain": domain,
                        "level": int(rule["level"]),
                        "pattern": str(rule["pattern"]),
                        "tier": str(rule["tier"]),
                        "authority": float(rule["authority"]),
                        "note": rule.get("note"),
                        "active": True,
                    }
                )
                inserted += 1
            except Exception:
                # 중복/스키마 문제 등은 스킵하고 다음 규칙으로
                continue
    return inserted


# ─────────────────────────────────────────────────────────────
# 조회
# ─────────────────────────────────────────────────────────────
async def lookup_authority(source: str, domain: str) -> tuple[str, float]:
    """`source` 를 `domain` 규칙들과 대조해 (tier, authority) 를 반환.

    - 도메인에 규칙이 없으면 ``general`` 규칙을 fallback 으로 본다.
    - 어떤 규칙에도 매칭되지 않으면 ``("UNKNOWN", 0.3)``.
    - 매칭이 여럿이면 `level` 이 가장 작은 것(=상위)을 채택.
    """
    host = extract_host(source)
    raw = (source or "").strip()

    try:
        rules = await prisma.sourcehierarchyrule.find_many(
            where={"domain": domain, "active": True},
            order={"level": "asc"},
        )
    except Exception:
        rules = []

    if not rules and domain != "general":
        try:
            rules = await prisma.sourcehierarchyrule.find_many(
                where={"domain": "general", "active": True},
                order={"level": "asc"},
            )
        except Exception:
            rules = []

    for rule in rules:
        if _match_pattern(rule.pattern, host, raw):
            tier = str(getattr(rule, "tier", "UNKNOWN") or "UNKNOWN")
            authority = float(getattr(rule, "authority", 0.3) or 0.3)
            return (tier, authority)

    return ("UNKNOWN", 0.3)


async def classify_source_by_hierarchy(source: str, domain: str) -> dict[str, Any]:
    """`lookup_authority` 결과 + 매칭된 rule 의 level/id 를 함께 반환."""
    host = extract_host(source)
    raw = (source or "").strip()

    try:
        rules = await prisma.sourcehierarchyrule.find_many(
            where={"domain": domain, "active": True},
            order={"level": "asc"},
        )
    except Exception:
        rules = []

    if not rules and domain != "general":
        try:
            rules = await prisma.sourcehierarchyrule.find_many(
                where={"domain": "general", "active": True},
                order={"level": "asc"},
            )
        except Exception:
            rules = []

    for rule in rules:
        if _match_pattern(rule.pattern, host, raw):
            return {
                "source": source,
                "host": host,
                "domain": domain,
                "rule_id": rule.id,
                "level": int(rule.level),
                "tier": str(rule.tier),
                "authority": float(rule.authority),
                "pattern": rule.pattern,
                "matched": True,
            }

    return {
        "source": source,
        "host": host,
        "domain": domain,
        "rule_id": None,
        "level": None,
        "tier": "UNKNOWN",
        "authority": 0.3,
        "pattern": None,
        "matched": False,
    }


# ─────────────────────────────────────────────────────────────
# 규칙 CRUD
# ─────────────────────────────────────────────────────────────
async def add_hierarchy_rule(
    domain: str,
    level: int,
    pattern: str,
    tier: str,
    authority: float,
    note: str | None = None,
) -> str:
    """새 위계 규칙 추가. 생성된 id 반환."""
    # 패턴이 컴파일 가능한지 사전 검증 (잘못된 regex 저장 방지)
    try:
        re.compile(pattern)
    except re.error as e:
        raise ValueError(f"invalid regex pattern: {e}") from e

    created = await prisma.sourcehierarchyrule.create(
        data={
            "domain": domain,
            "level": int(level),
            "pattern": pattern,
            "tier": tier,
            "authority": max(0.0, min(1.0, float(authority))),
            "note": note,
            "active": True,
        }
    )
    return created.id


async def update_hierarchy_rule(rule_id: str, **kwargs: Any) -> None:
    """기존 규칙 수정. 허용 필드: domain/level/pattern/tier/authority/note/active."""
    allowed = {"domain", "level", "pattern", "tier", "authority", "note", "active"}
    data: dict[str, Any] = {}
    for k, v in kwargs.items():
        if k not in allowed:
            continue
        if k == "pattern" and isinstance(v, str):
            try:
                re.compile(v)
            except re.error as e:
                raise ValueError(f"invalid regex pattern: {e}") from e
        if k == "authority" and v is not None:
            v = max(0.0, min(1.0, float(v)))
        if k == "level" and v is not None:
            v = int(v)
        data[k] = v
    if not data:
        return
    await prisma.sourcehierarchyrule.update(where={"id": rule_id}, data=data)


async def deactivate_rule(rule_id: str) -> None:
    """규칙을 soft-disable (active=False)."""
    await prisma.sourcehierarchyrule.update(
        where={"id": rule_id}, data={"active": False}
    )


async def list_rules(
    domain: str | None = None, tier: str | None = None
) -> list[dict[str, Any]]:
    """규칙 목록. 도메인/티어 필터 지원. level 오름차순 정렬."""
    where: dict[str, Any] = {"active": True}
    if domain:
        where["domain"] = domain
    if tier:
        where["tier"] = tier

    rows = await prisma.sourcehierarchyrule.find_many(
        where=where, order={"level": "asc"}
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "domain": r.domain,
                "level": int(r.level),
                "pattern": r.pattern,
                "tier": str(r.tier),
                "authority": float(r.authority),
                "note": r.note,
                "active": bool(r.active),
            }
        )
    return out


# ─────────────────────────────────────────────────────────────
# 사실에 위계 적용
# ─────────────────────────────────────────────────────────────
async def apply_hierarchy_to_fact(fact_id: str) -> dict[str, Any]:
    """한 건의 `KnowledgeFact` 에 위계를 적용.

    `source_url` 이 있으면 그것을, 없으면 `source` 이름을 매칭에 사용한다.
    반환값은 변경 전/후 값 요약.
    """
    fact = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if not fact:
        return {
            "fact_id": fact_id,
            "old_tier": None,
            "new_tier": None,
            "old_authority": None,
            "new_authority": None,
            "updated": False,
        }

    source = fact.sourceUrl or fact.source or ""
    domain = fact.domain or "general"

    tier, authority = await lookup_authority(source, domain)

    old_tier = str(fact.sourceTier) if fact.sourceTier else None
    old_authority = float(fact.sourceAuthority) if fact.sourceAuthority is not None else None

    await prisma.knowledgefact.update(
        where={"id": fact_id},
        data={"sourceTier": tier, "sourceAuthority": authority},
    )

    return {
        "fact_id": fact_id,
        "old_tier": old_tier,
        "new_tier": tier,
        "old_authority": old_authority,
        "new_authority": authority,
        "updated": True,
    }


async def bulk_apply_hierarchy(
    domain: str | None = None, batch: int = 500
) -> dict[str, Any]:
    """배치로 여러 사실에 위계 적용.

    `domain` 이 주어지면 해당 도메인만 처리. batch 크기 단위로 커서를 넘기며 순회.
    반환: 처리/갱신/스킵 카운트.
    """
    processed = 0
    updated = 0
    skipped = 0

    where: dict[str, Any] = {}
    if domain:
        where["domain"] = domain

    cursor: str | None = None
    while True:
        kwargs: dict[str, Any] = {
            "where": where,
            "take": batch,
            "order": {"id": "asc"},
        }
        if cursor:
            kwargs["cursor"] = {"id": cursor}
            kwargs["skip"] = 1

        facts = await prisma.knowledgefact.find_many(**kwargs)
        if not facts:
            break

        for f in facts:
            processed += 1
            source = f.sourceUrl or f.source or ""
            fdomain = f.domain or "general"
            tier, authority = await lookup_authority(source, fdomain)

            # 변화가 없으면 쓰지 않는다 (불필요한 쓰기 방지).
            cur_tier = str(f.sourceTier) if f.sourceTier else None
            cur_auth = float(f.sourceAuthority) if f.sourceAuthority is not None else None
            if cur_tier == tier and cur_auth is not None and abs(cur_auth - authority) < 1e-6:
                skipped += 1
                continue

            try:
                await prisma.knowledgefact.update(
                    where={"id": f.id},
                    data={"sourceTier": tier, "sourceAuthority": authority},
                )
                updated += 1
            except Exception:
                skipped += 1

        if len(facts) < batch:
            break
        cursor = facts[-1].id

    return {
        "processed": processed,
        "updated": updated,
        "skipped": skipped,
        "domain": domain,
    }


__all__ = [
    "DEFAULT_HIERARCHY",
    "extract_host",
    "seed_default_hierarchy",
    "lookup_authority",
    "classify_source_by_hierarchy",
    "add_hierarchy_rule",
    "update_hierarchy_rule",
    "deactivate_rule",
    "list_rules",
    "apply_hierarchy_to_fact",
    "bulk_apply_hierarchy",
]
