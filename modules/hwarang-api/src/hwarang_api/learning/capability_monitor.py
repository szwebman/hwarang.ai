"""HSEE Phase 3 — 도메인별 능력 측정 (Capability Monitor).

매일 자정 cron 으로 호출. 7 일 윈도우 기본.

측정 항목 (CapabilityMetric 테이블에 기록):
- ``benchmarkScore``     : 자체 벤치마크 정확도 (forgetting_metric 의 _run_benchmark 재활용)
- ``satisfactionAvg``    : RLHFFeedback.isSatisfied 평균 (0~1)
- ``factualAccuracy``    : SourceCitation 결합 confidence 평균
- ``responseLatencyMs``  : RoutingStats 도메인별 평균
- ``failureRate``        : 답변 거부 / 폴백 비율
- ``unmatchedRate``      : 도메인 미매칭 — 도메인 분류 됐는데 general 모델이 처리한 비율

Phase 3 의 다른 모듈 (auto_spawn, growth_planner) 이 이 메트릭을 입력으로 받아
구조 성장 결정을 내린다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


# 기본 도메인 — 동적으로 EmergentDomain 승격 시 확장 가능
DOMAINS = ["legal", "tax", "medical", "coding", "finance", "general"]

# 임계치 (auto_spawn / scale_decision 이 참고)
THRESHOLD_LOW_SATISFACTION = 0.7
THRESHOLD_LOW_FACTUAL = 0.6
THRESHOLD_HIGH_UNMATCHED = 0.3
THRESHOLD_HIGH_FAILURE = 0.2


def _prisma_ready() -> bool:
    try:
        return bool(prisma.is_connected())
    except Exception:
        return False


# ────────────────────────────────────────────────────────────
# 메인 API
# ────────────────────────────────────────────────────────────
async def measure_all_domains(window_days: int = 7) -> dict[str, dict[str, Any]]:
    """모든 도메인 측정 + DB 기록.

    Returns
    -------
    dict
        ``{domain: metric_dict}`` 형태.
    """
    if not _prisma_ready():
        return {}

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=window_days)

    # EmergentDomain 중 isPromoted 된 것들도 측정 대상에 포함
    domains: list[str] = list(DOMAINS)
    try:
        promoted = await prisma.emergentdomain.find_many(
            where={"isPromoted": True},
        )
        for e in promoted:
            if e.candidateName not in domains:
                domains.append(e.candidateName)
    except Exception as e:  # pragma: no cover
        logger.debug(f"EmergentDomain 조회 skip: {e}")

    results: dict[str, dict[str, Any]] = {}
    for d in domains:
        try:
            metric = await measure_domain(d, start, end)
            await prisma.capabilitymetric.create(
                data={
                    "domain": d,
                    "windowStart": start,
                    "windowEnd": end,
                    **metric,
                }
            )
            results[d] = metric
        except Exception as e:  # pragma: no cover
            logger.warning(f"measure_domain({d}) 실패: {e}")
            results[d] = {"error": str(e)}
    return results


async def measure_domain(
    domain: str,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    """단일 도메인 능력 측정 — DB 미저장. 메트릭 dict 반환.

    호출자가 ``CapabilityMetric.create`` 로 저장 (위 :func:`measure_all_domains` 참조).
    """
    domain = (domain or "general").strip().lower()

    # 1) RLHF 만족도
    satisfaction, sample_count = await _calc_satisfaction(domain, start, end)

    # 2) RoutingStats 기반 latency
    latency = await _calc_avg_latency(domain, start, end)

    # 3) 사실 정확도
    factual = await _calc_factual_accuracy(domain, start, end)

    # 4) 미매칭 비율
    unmatched = (
        await _calc_unmatched_rate(domain, start, end)
        if domain != "general"
        else 0.0
    )

    # 5) 응답 거부 / 폴백 비율
    failure = await _calc_failure_rate(domain, start, end)

    # 6) 자체 벤치마크 — 모델 인스턴스가 필요하므로 옵션. 가능하면 채움.
    bench = await _calc_benchmark_score(domain)

    return {
        "benchmarkScore": bench,
        "satisfactionAvg": satisfaction,
        "factualAccuracy": factual,
        "responseLatencyMs": latency,
        "failureRate": failure,
        "unmatchedRate": unmatched,
        "sampleCount": int(sample_count),
    }


# ────────────────────────────────────────────────────────────
# 개별 측정 함수
# ────────────────────────────────────────────────────────────
async def _calc_satisfaction(
    domain: str, start: datetime, end: datetime
) -> tuple[Optional[float], int]:
    """``RLHFFeedback.isSatisfied`` 평균. 표본이 0 이면 None."""
    try:
        feedback = await prisma.rlhffeedback.find_many(
            where={
                "domain": domain,
                "createdAt": {"gte": start, "lte": end},
                "isSatisfied": {"not": None},
            },
        )
    except Exception as e:  # pragma: no cover
        logger.debug(f"RLHFFeedback 조회 실패: {e}")
        return None, 0

    if not feedback:
        return None, 0

    positive = sum(1 for f in feedback if f.isSatisfied)
    return positive / len(feedback), len(feedback)


async def _calc_avg_latency(
    domain: str, start: datetime, end: datetime
) -> Optional[float]:
    """``RoutingStats`` 의 totalLatencyMs / totalRequests 가중 평균."""
    try:
        rows = await prisma.routingstats.find_many(
            where={"domain": domain, "windowStart": {"gte": start, "lte": end}},
        )
    except Exception:  # pragma: no cover
        return None

    total_lat = sum(int(r.totalLatencyMs or 0) for r in rows)
    total_req = sum(int(r.totalRequests or 0) for r in rows)
    if total_req == 0:
        return None
    return float(total_lat) / float(total_req)


async def _calc_factual_accuracy(
    domain: str, start: datetime, end: datetime
) -> Optional[float]:
    """SourceCitation 이 있는 KnowledgeFact 의 ``confidenceT0`` 평균.

    출처 있는 fact / 전체 fact 비율과 평균 신뢰도를 곱한 값을 사용.
    """
    try:
        facts = await prisma.knowledgefact.find_many(
            where={
                "domain": domain,
                "createdAt": {"gte": start, "lte": end},
            },
        )
    except Exception:  # pragma: no cover
        return None

    if not facts:
        return None

    fact_ids = [f.id for f in facts]
    try:
        cite_facts = await prisma.sourcecitation.find_many(
            where={"factId": {"in": fact_ids}},
        )
    except Exception:  # pragma: no cover
        cite_facts = []

    cited = {c.factId for c in cite_facts if c.factId}
    coverage = len(cited) / len(facts)
    avg_conf = sum(float(f.confidenceT0 or 0.0) for f in facts) / len(facts)
    return coverage * avg_conf


async def _calc_unmatched_rate(
    domain: str, start: datetime, end: datetime
) -> float:
    """도메인 분류 됐는데 ``general`` 모델이 처리한 비율.

    근사: ``RLHFFeedback`` 에서 ``domain==<domain>`` 이지만 ``modelName`` 이
    general 류 (이름에 'general' 포함) 인 비율.
    """
    try:
        rows = await prisma.rlhffeedback.find_many(
            where={"domain": domain, "createdAt": {"gte": start, "lte": end}},
        )
    except Exception:  # pragma: no cover
        return 0.0

    if not rows:
        return 0.0

    fallback = sum(
        1 for r in rows if (r.modelName or "").lower().find("general") >= 0
    )
    return fallback / len(rows)


async def _calc_failure_rate(
    domain: str, start: datetime, end: datetime
) -> float:
    """응답 거부 / 폴백 비율 — RLHFFeedback.rating == -1 이거나
    isSatisfied == False 인 비율."""
    try:
        rows = await prisma.rlhffeedback.find_many(
            where={"domain": domain, "createdAt": {"gte": start, "lte": end}},
        )
    except Exception:  # pragma: no cover
        return 0.0
    if not rows:
        return 0.0
    bad = sum(1 for r in rows if r.rating == -1 or r.isSatisfied is False)
    return bad / len(rows)


async def _calc_benchmark_score(domain: str) -> Optional[float]:
    """자체 벤치마크 점수 (forgetting_metric 재활용).

    벤치마크 jsonl 이 없으면 None.
    모델 인스턴스를 직접 잡지 않고 ``HSEE_BENCHMARK_DIR`` 의 expected 답과의
    최근 응답 매칭률을 사용. 실제 모델 호출이 필요한 평가는 외부 워커에 위임.
    """
    # 본격 평가는 외부 워커가 ``benchmarkScore`` 를 별도로 채워 넣음.
    # 여기서는 placeholder — 데이터가 없으면 None.
    return None


# ────────────────────────────────────────────────────────────
# 조회 헬퍼 — 라우터 / auto_spawn / scale_decision 이 사용
# ────────────────────────────────────────────────────────────
async def list_recent_metrics(
    domain: Optional[str] = None,
    days: int = 30,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """최근 ``days`` 일 메트릭 list — 관리자 조회용."""
    if not _prisma_ready():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    where: dict[str, Any] = {"measuredAt": {"gte": cutoff}}
    if domain:
        where["domain"] = domain
    try:
        rows = await prisma.capabilitymetric.find_many(
            where=where,
            order={"measuredAt": "desc"},
            take=limit,
        )
    except Exception:  # pragma: no cover
        return []
    return [_metric_to_dict(r) for r in rows]


async def latest_per_domain(days: int = 7) -> dict[str, dict[str, Any]]:
    """도메인별 최신 메트릭 1 건씩."""
    if not _prisma_ready():
        return {}
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = await prisma.capabilitymetric.find_many(
        where={"measuredAt": {"gte": cutoff}},
        order={"measuredAt": "desc"},
    )
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r.domain not in out:
            out[r.domain] = _metric_to_dict(r)
    return out


def _metric_to_dict(r: Any) -> dict[str, Any]:
    return {
        "id": r.id,
        "domain": r.domain,
        "loraName": r.loraName,
        "measuredAt": r.measuredAt.isoformat() if r.measuredAt else None,
        "windowStart": r.windowStart.isoformat() if r.windowStart else None,
        "windowEnd": r.windowEnd.isoformat() if r.windowEnd else None,
        "benchmarkScore": r.benchmarkScore,
        "satisfactionAvg": r.satisfactionAvg,
        "factualAccuracy": r.factualAccuracy,
        "responseLatencyMs": r.responseLatencyMs,
        "failureRate": r.failureRate,
        "unmatchedRate": r.unmatchedRate,
        "sampleCount": r.sampleCount,
    }


__all__ = [
    "DOMAINS",
    "THRESHOLD_LOW_SATISFACTION",
    "THRESHOLD_LOW_FACTUAL",
    "THRESHOLD_HIGH_UNMATCHED",
    "THRESHOLD_HIGH_FAILURE",
    "measure_all_domains",
    "measure_domain",
    "list_recent_metrics",
    "latest_per_domain",
]
