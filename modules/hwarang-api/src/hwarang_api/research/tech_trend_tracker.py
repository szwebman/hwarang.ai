"""주간 코딩/디자인 트렌드 분석 — Group C.

매주 일요일 22:00 KST cron 으로 실행:

1. 지난 주 vs 4 주 baseline (3 주 평균) 키워드/태그 빈도 비교.
2. 30 % + 증가 = ``isEmerging`` 으로 표시.
3. ``PaperTrend`` 와 별도로 ``TechTrend`` 테이블에 기록 (도메인 = code | design).
4. Slack/Discord 알림 (notifier.notify_admin) — Group A 의 ``trend_tracker`` 와 동일 채널.
5. Application Engine 으로 화랑 LoRA 재학습 ``GrowthDecision`` 자동 생성.

사용::

    from hwarang_api.research.tech_trend_tracker import (
        weekly_tech_trends_full_cycle,
    )
    stats = await weekly_tech_trends_full_cycle()

설계 메모:
    - 코드 키워드는 ``KNOWN_TECH_KEYWORDS`` 화이트리스트로 추출 (LLM 비용 0 ↔ 정확도↑).
    - 디자인은 ``DesignPattern.trendKeywords`` 가 이미 LLM 분류된 단어이므로 그대로 사용.
    - ``baseline = 0`` 인 신규 키워드는 ``BASELINE_FLOOR`` 로 분모 하한을 둬서
      divide-by-zero / +∞ 를 막는다.
    - emerging 임계치는 두 도메인 다르게 설정 — 코드는 노이즈가 많아 3건/+30%,
      디자인은 패턴 자체가 적어 2건/+30%.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


# ─── 임계치 ─────────────────────────────────────────────
EMERGING_VELOCITY_PCT = 30.0
EMERGING_MIN_CODE = 3       # 코드는 노이즈 많음 → 최소 3건
EMERGING_MIN_DESIGN = 2     # 디자인 패턴은 수량 적음 → 최소 2건
BASELINE_FLOOR = 0.5
GROWTH_TRIGGER_CODE = 5     # emerging 5+ 시 LoRA 학습 제안
GROWTH_TRIGGER_DESIGN = 3


# ─── 알려진 기술 키워드 화이트리스트 ───────────────────
# code_pattern_extractor 의 LLM 답변과 별개로, KnowledgeFact.content
# 본문에서 직접 빈도를 셀 키워드. 너무 일반적 단어 (data, file 등) 제외.
KNOWN_TECH_KEYWORDS: list[str] = [
    # 언어
    "python", "javascript", "typescript", "rust", "go ", "java", "kotlin",
    "swift", "elixir", "ruby", "scala", "zig",
    # 프론트 프레임워크/라이브러리
    "react", "next.js", "vue", "svelte", "sveltekit", "angular", "solid",
    "qwik", "remix", "astro", "nuxt",
    # 백엔드
    "fastapi", "django", "flask", "express", "nestjs", "axum", "actix",
    "spring boot", "rails",
    # AI / ML
    "pytorch", "tensorflow", "transformers", "vllm", "langchain",
    "llamaindex", "ollama", "huggingface",
    # CSS / UI
    "tailwindcss", "shadcn", "radix", "chakra", "mui", "framer motion",
    # 인프라
    "docker", "kubernetes", "k8s", "aws", "vercel", "cloudflare",
    "supabase", "neon", "planetscale", "fly.io", "railway",
    # AI 기법
    "lora", "qlora", "rlhf", "dpo", "moe", "rag", "agent",
    # 모델
    "claude", "gpt", "gemini", "llama", "qwen", "mistral", "deepseek",
    "exaone", "phi-3", "phi-4",
]


# ─── 코드 트렌드 ────────────────────────────────────────
async def weekly_code_trends() -> dict:
    """``domain="code"`` KnowledgeFact 의 키워드 분석."""
    now = datetime.now(timezone.utc)
    this_week_start = now - timedelta(days=7)
    four_weeks_ago = now - timedelta(days=28)

    try:
        this_week = await prisma.knowledgefact.find_many(
            where={
                "domain": "code",
                "createdAt": {"gte": this_week_start},
            },
            take=1000,
        )
        baseline = await prisma.knowledgefact.find_many(
            where={
                "domain": "code",
                "createdAt": {
                    "gte": four_weeks_ago,
                    "lt": this_week_start,
                },
            },
            take=3000,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("weekly_code_trends DB 실패: %s", exc)
        return {"trends": 0, "reason": "db_error"}

    if not this_week:
        return {"trends": 0, "reason": "no_recent"}

    this_kw = _extract_tech_keywords(this_week)
    base_kw = _extract_tech_keywords(baseline)
    base_weekly = {k: v / 3.0 for k, v in base_kw.items()}  # 3주 평균

    week_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    saved = 0
    emerging: list[dict] = []
    for kw, this_count in this_kw.most_common(100):
        base_count = base_weekly.get(kw, BASELINE_FLOOR)
        denom = max(base_count, BASELINE_FLOOR)
        velocity = ((this_count - base_count) / denom) * 100.0
        is_emerging = (
            velocity >= EMERGING_VELOCITY_PCT and this_count >= EMERGING_MIN_CODE
        )
        if await _upsert_trend(
            week_start, "code", kw, this_count, velocity, is_emerging
        ):
            saved += 1
        if is_emerging:
            emerging.append({"keyword": kw, "velocity_pct": velocity})

    top_emerging = [
        t["keyword"]
        for t in sorted(emerging, key=lambda x: -x["velocity_pct"])[:5]
    ]
    return {
        "this_week_facts": len(this_week),
        "baseline_facts": len(baseline),
        "saved_trends": saved,
        "emerging_count": len(emerging),
        "top_emerging": top_emerging,
    }


# ─── 디자인 트렌드 ──────────────────────────────────────
async def weekly_design_trends() -> dict:
    """``DesignPattern.trendKeywords`` 분석."""
    now = datetime.now(timezone.utc)
    this_week_start = now - timedelta(days=7)
    four_weeks_ago = now - timedelta(days=28)

    try:
        this_patterns = await prisma.designpattern.find_many(
            where={"createdAt": {"gte": this_week_start}},
            take=500,
        )
        baseline_patterns = await prisma.designpattern.find_many(
            where={
                "createdAt": {
                    "gte": four_weeks_ago,
                    "lt": this_week_start,
                }
            },
            take=1500,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("weekly_design_trends DB 실패: %s", exc)
        return {"trends": 0, "reason": "db_error"}

    if not this_patterns:
        return {"trends": 0, "reason": "no_recent"}

    this_kw: Counter[str] = Counter()
    for p in this_patterns:
        for k in (getattr(p, "trendKeywords", None) or []):
            this_kw[(k or "").strip().lower()] += 1

    base_kw: Counter[str] = Counter()
    for p in baseline_patterns:
        for k in (getattr(p, "trendKeywords", None) or []):
            base_kw[(k or "").strip().lower()] += 1

    base_weekly = {k: v / 3.0 for k, v in base_kw.items()}
    week_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    saved = 0
    emerging: list[dict] = []
    for kw, this_count in this_kw.most_common(50):
        if not kw:
            continue
        base_count = base_weekly.get(kw, BASELINE_FLOOR)
        denom = max(base_count, BASELINE_FLOOR)
        velocity = ((this_count - base_count) / denom) * 100.0
        is_emerging = (
            velocity >= EMERGING_VELOCITY_PCT
            and this_count >= EMERGING_MIN_DESIGN
        )
        if await _upsert_trend(
            week_start, "design", kw, this_count, velocity, is_emerging
        ):
            saved += 1
        if is_emerging:
            emerging.append({"keyword": kw, "velocity_pct": velocity})

    top_emerging = [
        t["keyword"]
        for t in sorted(emerging, key=lambda x: -x["velocity_pct"])[:5]
    ]
    return {
        "this_week_patterns": len(this_patterns),
        "baseline_patterns": len(baseline_patterns),
        "saved_trends": saved,
        "emerging_count": len(emerging),
        "top_emerging": top_emerging,
    }


# ─── 풀 사이클 ──────────────────────────────────────────
async def weekly_tech_trends_full_cycle() -> dict:
    """매주 cron — 코드 + 디자인 트렌드 동시 분석 + 알림 + LoRA 제안."""
    code_result = await weekly_code_trends()
    design_result = await weekly_design_trends()

    # 알림 (둘 중 하나라도 emerging 이 있으면)
    if (
        code_result.get("top_emerging")
        or design_result.get("top_emerging")
    ):
        await _notify_trends(code_result, design_result)

    # Application Engine 으로 LoRA 재학습 GrowthDecision 자동 제안
    await _propose_lora_updates(code_result, design_result)

    return {"code": code_result, "design": design_result}


# ─── 조회 (관리자 UI 용) ───────────────────────────────
async def get_recent_tech_trends(
    domain: str | None = None,
    weeks: int = 4,
    only_emerging: bool = False,
) -> list:
    """최근 N 주 ``TechTrend`` 조회 — 관리자 UI 가 호출."""
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=weeks)
    where: dict = {"weekStart": {"gte": cutoff}}
    if domain:
        where["domain"] = domain
    if only_emerging:
        where["isEmerging"] = True

    try:
        trends = await prisma.techtrend.find_many(
            where=where,
            order=[{"weekStart": "desc"}, {"velocityPct": "desc"}],
            take=300,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("techtrend.find_many 실패: %s", exc)
        return []
    return trends


# ─── 인기 패턴 조회 ────────────────────────────────────
async def list_popular_code_patterns(
    language: str | None = None, top: int = 20
) -> list:
    where: dict = {}
    if language:
        where["language"] = language
    try:
        return await prisma.codepattern.find_many(
            where=where,
            order=[{"popularity": "desc"}, {"createdAt": "desc"}],
            take=top,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("popular code patterns 실패: %s", exc)
        return []


async def list_popular_design_patterns(
    layout: str | None = None, top: int = 20
) -> list:
    where: dict = {}
    if layout:
        where["layoutCategory"] = layout
    try:
        return await prisma.designpattern.find_many(
            where=where,
            order=[{"popularity": "desc"}, {"createdAt": "desc"}],
            take=top,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("popular design patterns 실패: %s", exc)
        return []


# ─── 내부 헬퍼 ─────────────────────────────────────────
async def _upsert_trend(
    week_start: datetime,
    domain: str,
    keyword: str,
    count: int,
    velocity: float,
    is_emerging: bool,
) -> bool:
    """``TechTrend`` upsert. 모델/DB 미준비 시 silent False."""
    try:
        await prisma.techtrend.upsert(
            where={
                "weekStart_keyword_domain": {
                    "weekStart": week_start,
                    "keyword": keyword,
                    "domain": domain,
                }
            },
            data={
                "create": {
                    "weekStart": week_start,
                    "domain": domain,
                    "keyword": keyword,
                    "occurrences": count,
                    "velocityPct": velocity,
                    "isEmerging": is_emerging,
                },
                "update": {
                    "occurrences": count,
                    "velocityPct": velocity,
                    "isEmerging": is_emerging,
                },
            },
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("TechTrend upsert 실패 [%s/%s]: %s", domain, keyword, exc)
        return False


async def _propose_lora_updates(code_r: dict, design_r: dict) -> None:
    """떠오르는 트렌드 → 화랑 LoRA 재학습 제안 (``GrowthDecision``).

    조건:
      - code  : emerging_count >= 5  → hwarang-code-32b-v1 LoRA rank 확장 제안
      - design: emerging_count >= 3  → hwarang-design-v1 LoRA 재학습 제안

    중복 생성 방지를 위해 같은 주 같은 도메인의 ``proposed`` 가 이미 있으면
    skip. 관리자가 승인하면 Application Engine 이 실제 학습 잡으로 변환.
    """
    week_start = (
        datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        - timedelta(days=datetime.now(timezone.utc).weekday())
    )

    # 코드
    code_emerging = code_r.get("emerging_count", 0) or 0
    if code_emerging >= GROWTH_TRIGGER_CODE:
        await _create_growth_decision(
            domain="code",
            metric="emerging_tech_trends",
            value=float(code_emerging),
            proposal={
                "lora_name": "hwarang-code-32b-v1",
                "reason": (
                    f"이번 주 떠오르는 기술 키워드 {code_emerging}개 — "
                    f"학습 데이터 보강 필요"
                ),
                "emerging_keywords": code_r.get("top_emerging", []),
                "estimated_data_points": 1000,
                "week_start": week_start.isoformat(),
            },
        )

    # 디자인
    design_emerging = design_r.get("emerging_count", 0) or 0
    if design_emerging >= GROWTH_TRIGGER_DESIGN:
        await _create_growth_decision(
            domain="design",
            metric="emerging_design_trends",
            value=float(design_emerging),
            proposal={
                "lora_name": "hwarang-design-v1",
                "reason": (
                    f"이번 주 새 디자인 트렌드 {design_emerging}개"
                ),
                "emerging_keywords": design_r.get("top_emerging", []),
                "estimated_data_points": 500,
                "week_start": week_start.isoformat(),
            },
        )


async def _create_growth_decision(
    domain: str, metric: str, value: float, proposal: dict
) -> None:
    """중복 방지 로직 포함."""
    try:
        # 같은 도메인 + 메트릭 + proposed 가 7일 내에 이미 있으면 skip
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        existing = await prisma.growthdecision.find_first(
            where={
                "triggerDomain": domain,
                "triggerMetric": metric,
                "status": "proposed",
                "createdAt": {"gte": recent_cutoff},
            }
        )
        if existing:
            logger.info(
                "GrowthDecision 중복 — domain=%s metric=%s skip", domain, metric
            )
            return
    except Exception:  # noqa: BLE001
        # find_first 가 모델 없을 때도 그냥 생성 시도
        pass

    try:
        await prisma.growthdecision.create(
            data={
                "decisionType": "expand_lora_rank",
                "triggerDomain": domain,
                "triggerMetric": metric,
                "triggerValue": value,
                "proposalJson": proposal,
                "status": "proposed",
            }
        )
        logger.info(
            "GrowthDecision 생성 — domain=%s metric=%s value=%s",
            domain,
            metric,
            value,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("GrowthDecision 생성 실패: %s", exc)


async def _notify_trends(code_r: dict, design_r: dict) -> None:
    """Slack/Discord 알림."""
    try:
        from hwarang_api.knowledge.notifier import notify_admin
    except ImportError:
        logger.debug("notifier 미사용 — trend alert skip")
        return

    text = "📈 *이번 주 코드 & 디자인 트렌드*\n\n"
    code_emerging = code_r.get("top_emerging") or []
    design_emerging = design_r.get("top_emerging") or []

    if code_emerging:
        text += "*💻 코드*: " + ", ".join(code_emerging[:5]) + "\n"
    else:
        text += "*💻 코드*: (이번 주 신규 emerging 없음)\n"

    if design_emerging:
        text += "*🎨 디자인*: " + ", ".join(design_emerging[:5]) + "\n"
    else:
        text += "*🎨 디자인*: (이번 주 신규 emerging 없음)\n"

    text += "\n관리자 UI: /research/code, /research/design, /research/trends"

    try:
        await notify_admin(
            text,
            severity="info",
            subject="[Hwarang] 주간 코드/디자인 트렌드",
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("notify_admin 실패: %s", exc)


# ─── 키워드 추출 (코드 도메인) ─────────────────────────
def _extract_tech_keywords(facts: list) -> Counter:
    """``KnowledgeFact.content`` 본문에서 ``KNOWN_TECH_KEYWORDS`` 빈도."""
    counter: Counter[str] = Counter()
    for f in facts:
        text = (getattr(f, "content", None) or "").lower()
        if not text:
            continue
        for kw in KNOWN_TECH_KEYWORDS:
            # "go " 같이 trailing space 가 있는 키워드는 그대로 매칭 (단어 경계 효과)
            if kw in text:
                counter[kw.strip()] += 1
    return counter


__all__ = [
    "weekly_code_trends",
    "weekly_design_trends",
    "weekly_tech_trends_full_cycle",
    "get_recent_tech_trends",
    "list_popular_code_patterns",
    "list_popular_design_patterns",
    "EMERGING_VELOCITY_PCT",
    "EMERGING_MIN_CODE",
    "EMERGING_MIN_DESIGN",
    "GROWTH_TRIGGER_CODE",
    "GROWTH_TRIGGER_DESIGN",
    "KNOWN_TECH_KEYWORDS",
]
