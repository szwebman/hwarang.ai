"""주간 트렌드 분석 — 떠오르는 토픽 자동 감지.

매주 일요일 23:00 KST cron:
1. 지난 주 모든 Paper 키워드 빈도 집계
2. 4주 전 빈도 대비 증가율 계산 (3주 평균 baseline)
3. 30%+ 증가 키워드 = "emerging"
4. PaperTrend 테이블에 기록
5. Slack/Discord 로 emerging 트렌드 알림 (notifier.py 활용)
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


# 임계치
EMERGING_VELOCITY_PCT = 30.0    # baseline 대비 +30 % 이상이면 emerging
EMERGING_MIN_PAPERS = 3         # 이번 주 최소 N편 이상 (노이즈 제거)
BASELINE_FLOOR = 0.5            # baseline 0 → divide-by-zero 방지용 floor


async def weekly_trend_analysis() -> dict:
    """매주 1회 실행. 트렌드 계산 + 신규 emerging 알림."""
    now = datetime.now(timezone.utc)
    # 이번 주 (오늘부터 7일 전까지)
    this_week_start = now - timedelta(days=7)
    # 4 주 전 (비교 baseline)
    four_weeks_ago = now - timedelta(days=28)

    # 1. 이번 주 논문
    try:
        this_week = await prisma.paper.find_many(
            where={"publishedAt": {"gte": this_week_start}},
            take=500,
        )
        # 4 주 전 ~ 이번 주 직전 (3 주 평균 baseline)
        baseline = await prisma.paper.find_many(
            where={
                "publishedAt": {"gte": four_weeks_ago, "lt": this_week_start},
            },
            take=2000,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("trend paper.find_many 실패: %s", exc)
        return {"trends": 0, "reason": "db_error"}

    if not this_week:
        return {"trends": 0, "reason": "no_papers"}

    # 2. 키워드 빈도
    this_counter: Counter[str] = Counter()
    for p in this_week:
        for kw in (getattr(p, "keywords", None) or []):
            this_counter[kw.lower()] += 1

    baseline_counter: Counter[str] = Counter()
    for p in baseline:
        for kw in (getattr(p, "keywords", None) or []):
            baseline_counter[kw.lower()] += 1

    # 3주 평균으로 변환 (baseline 은 3주치)
    weekly_baseline = {k: v / 3.0 for k, v in baseline_counter.items()}

    # 3. 증가율 계산
    trends = []
    for kw, this_count in this_counter.items():
        base_count = weekly_baseline.get(kw, BASELINE_FLOOR)
        denom = max(base_count, BASELINE_FLOOR)
        velocity_pct = ((this_count - base_count) / denom) * 100.0

        # top 5 paper IDs 이번 주 매칭
        top_papers = [
            p.arxivId for p in this_week
            if kw in [k.lower() for k in (getattr(p, "keywords", None) or [])]
        ][:5]

        is_emerging = (
            velocity_pct >= EMERGING_VELOCITY_PCT
            and this_count >= EMERGING_MIN_PAPERS
        )

        trends.append({
            "keyword": kw,
            "paper_count": this_count,
            "baseline_count": base_count,
            "velocity_pct": velocity_pct,
            "top_papers": top_papers,
            "is_emerging": is_emerging,
        })

    # 4. PaperTrend upsert — 일요일 00:00 KST 기준 weekStart
    week_start = now - timedelta(days=now.weekday() + 1)
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    saved = 0
    emerging_keywords: list[dict] = []
    for t in trends:
        try:
            await prisma.papertrend.upsert(
                where={
                    "weekStart_keyword": {
                        "weekStart": week_start,
                        "keyword": t["keyword"],
                    }
                },
                data={
                    "create": {
                        "weekStart": week_start,
                        "keyword": t["keyword"],
                        "paperCount": t["paper_count"],
                        "velocityPct": t["velocity_pct"],
                        "topPapers": t["top_papers"],
                        "isEmerging": t["is_emerging"],
                    },
                    "update": {
                        "paperCount": t["paper_count"],
                        "velocityPct": t["velocity_pct"],
                        "topPapers": t["top_papers"],
                        "isEmerging": t["is_emerging"],
                    },
                },
            )
            saved += 1
            if t["is_emerging"]:
                emerging_keywords.append(t)
        except Exception as e:  # noqa: BLE001
            logger.debug("PaperTrend upsert 실패 %s: %s", t["keyword"], e)

    # 5. Emerging 트렌드 알림
    if emerging_keywords:
        await _notify_emerging_trends(emerging_keywords[:10])

    top_emerging = [
        t["keyword"]
        for t in sorted(emerging_keywords, key=lambda x: -x["velocity_pct"])[:5]
    ]

    return {
        "this_week_papers": len(this_week),
        "baseline_papers": len(baseline),
        "trends_recorded": saved,
        "emerging_count": len(emerging_keywords),
        "top_emerging": top_emerging,
    }


async def _notify_emerging_trends(emerging: list) -> None:
    """Slack/Discord/email 로 emerging 트렌드 알림 (notifier.notify_admin)."""
    try:
        from hwarang_api.knowledge.notifier import notify_admin
    except ImportError:
        logger.debug("notifier 미사용 — emerging alert skip")
        return

    text = "🚀 *이번 주 떠오르는 AI 트렌드*\n\n"
    for t in sorted(emerging, key=lambda x: -x["velocity_pct"])[:10]:
        text += (
            f"• `{t['keyword']}` — {t['paper_count']}편 "
            f"(전 주 대비 +{t['velocity_pct']:.0f}%)\n"
        )
    text += "\n관리자 UI 에서 자세히 보기: /admin/research/trends"

    try:
        await notify_admin(
            text,
            severity="info",
            subject="[Hwarang] 주간 AI 트렌드 리포트",
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("notify_admin 실패: %s", e)


async def get_recent_trends(weeks: int = 4, only_emerging: bool = False) -> list:
    """관리자 UI 가 호출 — 최근 N주 트렌드."""
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=weeks)
    where: dict = {"weekStart": {"gte": cutoff}}
    if only_emerging:
        where["isEmerging"] = True

    try:
        trends = await prisma.papertrend.find_many(
            where=where,
            order=[{"weekStart": "desc"}, {"velocityPct": "desc"}],
            take=200,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("papertrend.find_many 실패: %s", exc)
        return []
    return trends


__all__ = [
    "weekly_trend_analysis",
    "get_recent_trends",
    "EMERGING_VELOCITY_PCT",
    "EMERGING_MIN_PAPERS",
]
