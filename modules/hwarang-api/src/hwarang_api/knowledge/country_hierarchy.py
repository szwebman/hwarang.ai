"""HLKM TAL ③ — Country-Aware Source Hierarchy Registry.

국가별 공식 출처 위계 레지스트리.

한국(KR) 뿐만 아니라 미국(US), 일본(JP), 유럽연합(EU), 중국(CN), 국제기구(GLOBAL)
각각의 공식/학술/언론 출처를 국가 단위로 위계화한다. 같은 도메인(law/medical/
politics…)이라도 국가에 따라 "최상위 1차 출처"가 달라지므로, 사실의 **국가
기원(country of origin)** 을 먼저 인식한 뒤 해당 국가의 위계를 적용한다.

사용 예::

    # 출처에서 국가 추정
    country = detect_country_from_source("https://www.congress.gov/bill/...")
    # → "US"

    # 국가별 위계 조회
    tier, authority = await lookup_authority_by_country(
        "https://www.congress.gov/bill/...", "law", country="US"
    )
    # → ("PRIMARY_OFFICIAL", 1.0)

기존 :mod:`.hierarchy` 모듈은 KR 중심이었고, 본 모듈은 그 상위 확장판이다.
`SourceHierarchyRule.country` 컬럼(기본 "KR") 에 다국 데이터를 저장한다.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from hwarang_api.db import prisma

from .hierarchy import DEFAULT_HIERARCHY, extract_host, lookup_authority

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 국가별 위계 레지스트리 (시드)
# ─────────────────────────────────────────────────────────────
# level 이 작을수록 상위. 같은 도메인 안에서 level 오름차순으로 순회하며
# 처음 매칭되는 규칙의 tier/authority 를 채택한다.
COUNTRY_HIERARCHY: dict[str, dict[str, list[dict[str, Any]]]] = {
    "US": {
        "law": [
            {"level": 1, "pattern": r"(congress|senate|house)\.gov", "tier": "PRIMARY_OFFICIAL", "authority": 1.0, "note": "U.S. Congress"},
            {"level": 2, "pattern": r"supremecourt\.gov", "tier": "PRIMARY_OFFICIAL", "authority": 0.95, "note": "U.S. Supreme Court"},
            {"level": 3, "pattern": r"(law\.cornell|justia)\.", "tier": "SPECIALIZED_MEDIA", "authority": 0.8, "note": "법률 전문 DB"},
            {"level": 4, "pattern": r"(wsj|nytimes|washingtonpost)\.com", "tier": "GENERAL_MEDIA", "authority": 0.6, "note": "주요 일간지"},
        ],
        "medical": [
            {"level": 1, "pattern": r"(cdc|nih|fda)\.gov", "tier": "PRIMARY_OFFICIAL", "authority": 0.95, "note": "CDC/NIH/FDA"},
            {"level": 2, "pattern": r"(pubmed|nejm|jama|thelancet)", "tier": "PEER_REVIEWED", "authority": 0.97, "note": "동료심사 학술지"},
            {"level": 3, "pattern": r"mayoclinic\.org", "tier": "SPECIALIZED_MEDIA", "authority": 0.82, "note": "Mayo Clinic"},
        ],
        "politics": [
            {"level": 1, "pattern": r"whitehouse\.gov", "tier": "PRIMARY_OFFICIAL", "authority": 0.85, "note": "White House"},
            {"level": 2, "pattern": r"(nytimes|washingtonpost|wsj)\.com", "tier": "GENERAL_MEDIA", "authority": 0.6, "note": "주요 매체"},
            {"level": 3, "pattern": r"(foxnews|breitbart|huffpost|msnbc)\.com", "tier": "GENERAL_MEDIA", "authority": 0.4, "note": "편향 있음"},
        ],
    },
    "JP": {
        "law": [
            {"level": 1, "pattern": r"(shugiin|sangiin|courts)\.go\.jp", "tier": "PRIMARY_OFFICIAL", "authority": 1.0, "note": "국회/사법"},
            {"level": 2, "pattern": r"elaws\.e-gov\.go\.jp", "tier": "PRIMARY_OFFICIAL", "authority": 0.95, "note": "일본 법령"},
        ],
        "medical": [
            {"level": 1, "pattern": r"mhlw\.go\.jp", "tier": "PRIMARY_OFFICIAL", "authority": 0.95, "note": "후생노동성"},
            {"level": 2, "pattern": r"(niph|nibiohn)\.go\.jp", "tier": "PEER_REVIEWED", "authority": 0.9, "note": "국립연구기관"},
        ],
        "general": [
            {"level": 1, "pattern": r"(asahi|yomiuri|mainichi|sankei|nikkei)\.com", "tier": "GENERAL_MEDIA", "authority": 0.6, "note": "주요 일간지"},
        ],
    },
    "EU": {
        "law": [
            {"level": 1, "pattern": r"(eur-lex|europa)\.eu", "tier": "PRIMARY_OFFICIAL", "authority": 1.0, "note": "EU 법령"},
            {"level": 2, "pattern": r"europarl\.europa\.eu", "tier": "PRIMARY_OFFICIAL", "authority": 0.95, "note": "유럽의회"},
        ],
        "medical": [
            {"level": 1, "pattern": r"ema\.europa\.eu", "tier": "PRIMARY_OFFICIAL", "authority": 0.95, "note": "유럽의약품청"},
            {"level": 2, "pattern": r"ecdc\.europa\.eu", "tier": "PRIMARY_OFFICIAL", "authority": 0.9, "note": "ECDC"},
        ],
    },
    "CN": {
        "law": [
            {"level": 1, "pattern": r"(npc|court)\.gov\.cn", "tier": "PRIMARY_OFFICIAL", "authority": 0.9, "note": "중국 공식 — 정치적 편향 고려"},
        ],
        "general": [
            {"level": 1, "pattern": r"(xinhuanet|people|cctv)\.cn", "tier": "GENERAL_MEDIA", "authority": 0.5, "note": "국영 매체 — 편향 있음"},
        ],
    },
    "GLOBAL": {
        "medical": [
            {"level": 1, "pattern": r"who\.int", "tier": "PRIMARY_OFFICIAL", "authority": 0.95, "note": "WHO"},
            {"level": 2, "pattern": r"(un\.org|unicef)", "tier": "PRIMARY_OFFICIAL", "authority": 0.9, "note": "UN/UNICEF"},
        ],
        "tech": [
            {"level": 1, "pattern": r"(ieee|acm|w3|ietf)\.org", "tier": "PEER_REVIEWED", "authority": 0.95, "note": "국제 표준/학회"},
        ],
    },
}


COUNTRY_DISPLAY_NAMES: dict[str, str] = {
    "KR": "한국",
    "US": "미국",
    "JP": "일본",
    "EU": "유럽연합",
    "CN": "중국",
    "GLOBAL": "국제기구",
    "UNKNOWN": "미상",
}


# 국가 감지용 힌트 패턴 (URL/호스트 기반). 등록 순서대로 첫 매칭을 채택.
_COUNTRY_HINTS: list[tuple[str, str]] = [
    ("KR", r"\.(go|or)\.kr(/|$)"),
    ("KR", r"\.co\.kr(/|$)"),
    ("JP", r"\.go\.jp(/|$)"),
    ("JP", r"\.(co|or|ne)\.jp(/|$)"),
    ("CN", r"\.gov\.cn(/|$)"),
    ("CN", r"\.(com|net)\.cn(/|$)"),
    ("EU", r"\.europa\.eu(/|$)"),
    ("GLOBAL", r"(^|\.)who\.int(/|$)"),
    ("GLOBAL", r"(^|\.)un\.org(/|$)"),
    ("GLOBAL", r"(^|\.)unicef\.org(/|$)"),
    ("GLOBAL", r"(^|\.)(ieee|acm|w3|ietf)\.org(/|$)"),
    # .gov 는 US 국가 도메인의 관용.
    ("US", r"\.gov(/|$)"),
    ("US", r"\.mil(/|$)"),
    ("US", r"(^|\.)(nytimes|washingtonpost|wsj|foxnews|cnn|nbcnews|cbsnews|breitbart|huffpost|msnbc|nejm|jama|thelancet|mayoclinic)\.(com|org)(/|$)"),
]


# ─────────────────────────────────────────────────────────────
# 패턴 매칭 유틸
# ─────────────────────────────────────────────────────────────
def _match_pattern(pattern: str, host: str, raw: str) -> bool:
    """정규식 패턴을 호스트/원문에 매칭."""
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
# 국가 감지
# ─────────────────────────────────────────────────────────────
def detect_country_from_source(source: str) -> str:
    """URL/출처명에서 국가 힌트를 추출.

    규칙:
      - ``.go.kr`` / ``.co.kr``        → ``KR``
      - ``.gov``  / ``.mil``           → ``US``
      - 주요 미국 매체(nytimes, wsj …) → ``US``
      - ``.go.jp``                     → ``JP``
      - ``.europa.eu``                 → ``EU``
      - ``.gov.cn``                    → ``CN``
      - ``who.int`` / ``un.org`` 등    → ``GLOBAL``

    매칭 실패 시 ``"UNKNOWN"`` 반환.
    """
    if not source:
        return "UNKNOWN"

    host = extract_host(source)
    raw = source.strip().lower()

    for country, pattern in _COUNTRY_HINTS:
        if _match_pattern(pattern, host, raw):
            return country

    return "UNKNOWN"


# ─────────────────────────────────────────────────────────────
# 시드
# ─────────────────────────────────────────────────────────────
async def seed_country_hierarchy(countries: list[str] | None = None) -> int:
    """`COUNTRY_HIERARCHY` 를 DB 에 시드.

    - ``countries`` 가 None 이면 전체 국가를 시드.
    - 기존 KR 레코드는 건드리지 않고 ``country`` 컬럼만 ``"KR"`` 로 채운다
      (legacy 데이터 마이그레이션).
    - 이미 같은 ``(country, domain, level, pattern)`` 조합이 있으면 스킵.

    반환값은 신규 삽입 수.
    """
    # 1) legacy 레코드의 country 컬럼을 KR 로 backfill
    try:
        await prisma.sourcehierarchyrule.update_many(
            where={"OR": [{"country": None}, {"country": ""}]},
            data={"country": "KR"},
        )
    except Exception as exc:  # noqa: BLE001
        # 스키마에 country 컬럼이 없거나, update_many 미지원이면 개별 경로로 진행.
        logger.debug("country backfill skipped: %s", exc)

    target_countries = (
        list(COUNTRY_HIERARCHY.keys()) if countries is None else list(countries)
    )

    inserted = 0
    for country in target_countries:
        registry = COUNTRY_HIERARCHY.get(country)
        if not registry:
            continue
        for domain, rules in registry.items():
            for rule in rules:
                try:
                    # 중복 체크
                    existing = await prisma.sourcehierarchyrule.find_first(
                        where={
                            "country": country,
                            "domain": domain,
                            "level": int(rule["level"]),
                            "pattern": str(rule["pattern"]),
                        }
                    )
                except Exception:
                    existing = None
                if existing:
                    continue
                try:
                    await prisma.sourcehierarchyrule.create(
                        data={
                            "country": country,
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
                except Exception as exc:  # noqa: BLE001
                    logger.debug("seed_country_hierarchy create failed (%s/%s): %s", country, domain, exc)
                    continue
    return inserted


# ─────────────────────────────────────────────────────────────
# 조회
# ─────────────────────────────────────────────────────────────
async def lookup_authority_by_country(
    source: str, domain: str, country: str | None = None
) -> tuple[str, float]:
    """국가를 명시해 `(tier, authority)` 조회.

    - ``country`` 가 주어지지 않으면 :func:`detect_country_from_source` 로 추정.
    - 매칭 실패 시 fallback 체인::

          <country> → GLOBAL → KR (legacy) → UNKNOWN

    최종적으로 ``("UNKNOWN", 0.3)`` 을 반환.
    """
    host = extract_host(source)
    raw = (source or "").strip()

    # 1) 국가 추정
    resolved_country = country or detect_country_from_source(source)

    candidate_countries: list[str] = []
    if resolved_country and resolved_country != "UNKNOWN":
        candidate_countries.append(resolved_country)
    if "GLOBAL" not in candidate_countries:
        candidate_countries.append("GLOBAL")
    if "KR" not in candidate_countries:
        # legacy: KR 은 기존 :mod:`.hierarchy` 데이터를 통해서도 커버.
        candidate_countries.append("KR")

    for c in candidate_countries:
        try:
            rules = await prisma.sourcehierarchyrule.find_many(
                where={"country": c, "domain": domain, "active": True},
                order={"level": "asc"},
            )
        except Exception:
            rules = []

        for rule in rules:
            if _match_pattern(rule.pattern, host, raw):
                return (
                    str(getattr(rule, "tier", "UNKNOWN") or "UNKNOWN"),
                    float(getattr(rule, "authority", 0.3) or 0.3),
                )

    # KR legacy 전용 fallback: hierarchy.lookup_authority 사용.
    # (마이그레이션 전에는 country 컬럼이 비어 있을 수 있다.)
    if resolved_country in ("KR", "UNKNOWN"):
        try:
            return await lookup_authority(source, domain)
        except Exception:
            pass

    return ("UNKNOWN", 0.3)


async def list_rules_by_country(country: str) -> list[dict[str, Any]]:
    """특정 국가의 모든 위계 규칙을 도메인/level 순으로 반환."""
    try:
        rows = await prisma.sourcehierarchyrule.find_many(
            where={"country": country, "active": True},
            order=[{"domain": "asc"}, {"level": "asc"}],
        )
    except Exception:
        rows = []

    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "country": getattr(r, "country", country),
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
# 사실 적용
# ─────────────────────────────────────────────────────────────
async def apply_country_to_fact(fact_id: str) -> dict[str, Any]:
    """한 건의 `KnowledgeFact` 에 국가 감지 + 국가별 위계를 재적용.

    동작:
      1. ``fact.sourceUrl`` 또는 ``fact.source`` 로 국가 감지
      2. 해당 국가의 위계에서 ``(tier, authority)`` 조회
      3. ``sourceTier`` / ``sourceAuthority`` 갱신
      4. 스키마에 ``country`` 필드가 있으면 함께 반영 (없으면 스킵)

    반환: 변경 전/후 요약.
    """
    fact = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if not fact:
        return {
            "fact_id": fact_id,
            "updated": False,
            "reason": "not_found",
        }

    source = getattr(fact, "sourceUrl", None) or getattr(fact, "source", "") or ""
    domain = getattr(fact, "domain", None) or "general"
    country = detect_country_from_source(source)

    tier, authority = await lookup_authority_by_country(source, domain, country=country)

    old_tier = str(fact.sourceTier) if getattr(fact, "sourceTier", None) else None
    old_authority = (
        float(fact.sourceAuthority) if getattr(fact, "sourceAuthority", None) is not None else None
    )

    update_data: dict[str, Any] = {
        "sourceTier": tier,
        "sourceAuthority": authority,
    }
    # KnowledgeFact 에 country 가 있을 수도, 없을 수도 있으므로 try 로 감싼다.
    try:
        await prisma.knowledgefact.update(
            where={"id": fact_id},
            data={**update_data, "country": country},
        )
    except Exception:
        try:
            await prisma.knowledgefact.update(
                where={"id": fact_id}, data=update_data
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("apply_country_to_fact update failed: %s", exc)
            return {
                "fact_id": fact_id,
                "updated": False,
                "reason": "update_error",
            }

    return {
        "fact_id": fact_id,
        "country": country,
        "old_tier": old_tier,
        "new_tier": tier,
        "old_authority": old_authority,
        "new_authority": authority,
        "updated": True,
    }


async def bulk_apply_country_hierarchy(
    country: str | None = None, limit: int = 500
) -> dict[str, Any]:
    """배치로 `KnowledgeFact` 들에 국가별 위계를 재적용.

    - ``country`` 가 주어지면 출처에서 추정된 국가가 일치하는 사실만 대상.
      (스키마에 ``KnowledgeFact.country`` 컬럼이 있으면 DB 필터로 선별.)
    - 한 번 호출당 최대 ``limit`` 건 처리.
    """
    processed = 0
    updated = 0
    skipped = 0
    by_country: dict[str, int] = {}

    where: dict[str, Any] = {}
    if country:
        # 스키마에 country 컬럼이 있을 때만 먹힌다. 아니면 예외 → 전체 스캔.
        where["country"] = country

    try:
        facts = await prisma.knowledgefact.find_many(
            where=where, take=limit, order={"id": "asc"}
        )
    except Exception:
        try:
            facts = await prisma.knowledgefact.find_many(take=limit, order={"id": "asc"})
        except Exception:
            facts = []

    for f in facts:
        processed += 1
        source = getattr(f, "sourceUrl", None) or getattr(f, "source", "") or ""
        fdomain = getattr(f, "domain", None) or "general"
        det_country = detect_country_from_source(source)

        # 국가 필터가 있고, DB 필터가 먹히지 않은 fallback 경로에서 추가 필터링.
        if country and det_country != country:
            skipped += 1
            continue

        tier, authority = await lookup_authority_by_country(source, fdomain, country=det_country)

        cur_tier = str(f.sourceTier) if getattr(f, "sourceTier", None) else None
        cur_auth = (
            float(f.sourceAuthority) if getattr(f, "sourceAuthority", None) is not None else None
        )
        if cur_tier == tier and cur_auth is not None and abs(cur_auth - authority) < 1e-6:
            # 변경 없음 → 카운트만 국가별로.
            by_country[det_country] = by_country.get(det_country, 0) + 1
            skipped += 1
            continue

        try:
            try:
                await prisma.knowledgefact.update(
                    where={"id": f.id},
                    data={"sourceTier": tier, "sourceAuthority": authority, "country": det_country},
                )
            except Exception:
                await prisma.knowledgefact.update(
                    where={"id": f.id},
                    data={"sourceTier": tier, "sourceAuthority": authority},
                )
            updated += 1
            by_country[det_country] = by_country.get(det_country, 0) + 1
        except Exception as exc:  # noqa: BLE001
            logger.debug("bulk_apply_country_hierarchy update failed: %s", exc)
            skipped += 1

    return {
        "processed": processed,
        "updated": updated,
        "skipped": skipped,
        "by_country": by_country,
        "country_filter": country,
    }


# ─────────────────────────────────────────────────────────────
# 국가 간 권위 비교
# ─────────────────────────────────────────────────────────────
async def compare_cross_country_authority(
    source_a: str, source_b: str, domain: str
) -> dict[str, Any]:
    """두 출처의 "자국 기준" 권위를 동시에 비교.

    동일 사안을 예컨대 미국(CDC)과 한국(KDCA)가 동시에 발표했을 때,
    각국 기준으로 모두 ``PRIMARY_OFFICIAL`` 일 수 있다. 이 함수는 각 출처가
    **자신의 국가 위계 안에서 갖는 권위** 를 나란히 반환해 "누구 말이 더
    공식적인가" 를 숫자로 비교할 수 있게 한다.
    """
    country_a = detect_country_from_source(source_a)
    country_b = detect_country_from_source(source_b)

    tier_a, auth_a = await lookup_authority_by_country(source_a, domain, country=country_a)
    tier_b, auth_b = await lookup_authority_by_country(source_b, domain, country=country_b)

    if abs(auth_a - auth_b) < 1e-6:
        winner = "tie"
    elif auth_a > auth_b:
        winner = "a"
    else:
        winner = "b"

    return {
        "a": {
            "source": source_a,
            "country": country_a,
            "country_name": COUNTRY_DISPLAY_NAMES.get(country_a, country_a),
            "tier": tier_a,
            "authority": auth_a,
        },
        "b": {
            "source": source_b,
            "country": country_b,
            "country_name": COUNTRY_DISPLAY_NAMES.get(country_b, country_b),
            "tier": tier_b,
            "authority": auth_b,
        },
        "domain": domain,
        "winner": winner,
    }


# ─────────────────────────────────────────────────────────────
# 사용자용 설명 (Markdown)
# ─────────────────────────────────────────────────────────────
async def fact_authority_explain(fact_id: str) -> str:
    """사실의 국가/티어/권위를 사람이 읽기 쉬운 한글 마크다운으로 설명."""
    fact = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if not fact:
        return f"- `{fact_id}` 사실을 찾을 수 없습니다."

    source = getattr(fact, "sourceUrl", None) or getattr(fact, "source", "") or ""
    domain = getattr(fact, "domain", None) or "general"
    country = getattr(fact, "country", None) or detect_country_from_source(source)
    country_name = COUNTRY_DISPLAY_NAMES.get(country, country)

    tier = str(getattr(fact, "sourceTier", None) or "UNKNOWN")
    authority = float(getattr(fact, "sourceAuthority", 0.0) or 0.0)

    # 값이 비어 있으면 현장에서 재조회
    if tier == "UNKNOWN" or authority == 0.0:
        tier, authority = await lookup_authority_by_country(source, domain, country=country)

    lines = [
        f"- **출처 국가**: {country_name} (`{country}`)",
        f"- **도메인**: `{domain}`",
        f"- **티어**: `{tier}`",
        f"- **권위 점수**: `{authority:.2f}` / 1.00",
        f"- **출처**: {source or '(미상)'}",
        "",
        f"이 사실의 출처는 **{country_name}**의 **{tier}** 급 출처로 분류되었으며, "
        f"권위 점수는 {authority:.2f} 입니다.",
    ]
    if tier == "UNKNOWN":
        lines.append(
            "> 위계에서 매칭되는 규칙을 찾지 못했습니다. 관리자가 규칙을 보강하면 더 정확한 평가가 가능합니다."
        )
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# 헬퍼 (디버깅/점검용)
# ─────────────────────────────────────────────────────────────
def _normalize_url(source: str) -> str:
    """URL 정규화 (스킴 없는 경우에도 host 만 추출 용도)."""
    if not source:
        return ""
    s = source.strip()
    if "://" not in s:
        s = "http://" + s
    try:
        return urlparse(s).netloc.lower()
    except Exception:
        return s.lower()


# merge-view: legacy KR :data:`DEFAULT_HIERARCHY` 와 새 COUNTRY_HIERARCHY 의
# KR 항목을 합쳐 보여주고 싶을 때 쓰는 조회 함수.
def get_merged_kr_hierarchy() -> dict[str, list[dict[str, Any]]]:
    """KR 한정: 기존 DEFAULT_HIERARCHY + COUNTRY_HIERARCHY["KR"] (있으면) 병합."""
    merged: dict[str, list[dict[str, Any]]] = {
        k: list(v) for k, v in DEFAULT_HIERARCHY.items()
    }
    kr = COUNTRY_HIERARCHY.get("KR", {})
    for domain, rules in kr.items():
        merged.setdefault(domain, [])
        merged[domain].extend(rules)
    return merged


__all__ = [
    "COUNTRY_HIERARCHY",
    "COUNTRY_DISPLAY_NAMES",
    "detect_country_from_source",
    "seed_country_hierarchy",
    "lookup_authority_by_country",
    "list_rules_by_country",
    "apply_country_to_fact",
    "bulk_apply_country_hierarchy",
    "compare_cross_country_authority",
    "fact_authority_explain",
    "get_merged_kr_hierarchy",
]
