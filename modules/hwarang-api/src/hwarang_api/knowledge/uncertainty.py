"""HLKM ⑧ - Uncertainty Quantification (불확실성 정량화).

점 추정 confidence 대신 **신뢰 구간** ``[lower, upper]`` 를 제공한다.
구간이 좁으면 "확실", 넓으면 "불확실" 이라는 질적 verdict 로 변환할 수
있다. 지원 방법:

  * bootstrap   : 경험적 품질 지표의 재표본 추출 → percentile
  * bayesian    : Beta prior + 지지/반박 관측 → credible interval
  * monte_carlo : 파라미터에 노이즈를 가해 arbitrated_confidence 를 반복 계산
  * ensemble    : 위 방법들의 중앙값 ± 1.96·σ

의존성:
  - numpy 가 있으면 사용, 없으면 pure Python 폴백
  - scipy 없이 Beta quantile 은 이분법 기반 근사
"""

from __future__ import annotations

import logging
import math
import random
from statistics import mean, median
from typing import Any

from hwarang_api.db import prisma

from .arbitrator import arbitrated_confidence
from .half_life import current_confidence
from .reputation import get_reputation
from .types import KnowledgeFact, KnowledgeStatus

logger = logging.getLogger(__name__)

try:  # pragma: no cover - 선택 의존성
    import numpy as _np  # type: ignore

    _HAS_NUMPY = True
except Exception:
    _HAS_NUMPY = False


# ─────────────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────────────
def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def std_from_samples(samples: list[float]) -> float:
    """numpy 없이 표준편차 (모분산 대신 표본분산, ddof=1)."""
    if not samples or len(samples) < 2:
        return 0.0
    if _HAS_NUMPY:
        return float(_np.std(samples, ddof=1))
    m = sum(samples) / len(samples)
    var = sum((x - m) ** 2 for x in samples) / (len(samples) - 1)
    return math.sqrt(var)


def _percentile(samples: list[float], q: float) -> float:
    """0~100 percentile — numpy 없으면 linear interpolation."""
    if not samples:
        return 0.0
    if _HAS_NUMPY:
        return float(_np.percentile(samples, q))
    s = sorted(samples)
    k = (len(s) - 1) * (q / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] + (s[c] - s[f]) * (k - f)


# ─────────────────────────────────────────────────────────────
# Beta quantile (scipy 없이)
# ─────────────────────────────────────────────────────────────
def _beta_cdf(x: float, a: float, b: float, terms: int = 400) -> float:
    """정규화된 incomplete beta 함수 근사 — 연속근사법.

    여기서는 간단한 수치 적분으로 대체하여 scipy 없이도 quantile 을 구한다.
    정확도는 quantile 계산에 충분.
    """
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    # 사다리꼴 적분
    n = max(200, terms)
    h = x / n
    total = 0.0
    # t=0 에서는 0 이므로 0부터 시작은 안전. pdf(t) = t^(a-1)(1-t)^(b-1) / B(a,b)
    # B(a,b) 는 정규화에만 영향 → 아래서 자체 정규화한다.
    prev = 0.0
    for i in range(1, n + 1):
        t = i * h
        val = (t ** (a - 1)) * ((1 - t) ** (b - 1))
        total += (prev + val) * 0.5 * h
        prev = val
    # 전체 정규화: B(a, b) = ∫0..1 t^(a-1)(1-t)^(b-1) dt
    norm = 0.0
    prev = 0.0
    n2 = max(400, terms)
    h2 = 1.0 / n2
    for i in range(1, n2 + 1):
        t = i * h2
        val = (t ** (a - 1)) * ((1 - t) ** (b - 1))
        norm += (prev + val) * 0.5 * h2
        prev = val
    if norm <= 0:
        return 0.0
    return max(0.0, min(1.0, total / norm))


def beta_quantile(alpha: float, beta: float, q: float) -> float:
    """Beta 분포의 q-quantile 을 이분법으로 근사. 0 < q < 1."""
    alpha = max(1e-3, float(alpha))
    beta = max(1e-3, float(beta))
    q = _clamp01(q)
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if _beta_cdf(mid, alpha, beta) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# ─────────────────────────────────────────────────────────────
# 품질 지표 수집
# ─────────────────────────────────────────────────────────────
async def _quality_signals(fact: KnowledgeFact) -> dict[str, float]:
    """부트스트랩 / 몬테카를로에서 샘플링할 품질 신호 집계."""
    time_decay = current_confidence(fact) if fact.valid_from else fact.confidence_t0
    try:
        source_rep = await get_reputation(fact.source)
    except Exception:
        source_rep = 0.5

    corroborations = 1
    if fact.entity:
        try:
            rows = await prisma.knowledgefact.find_many(
                where={"entity": fact.entity, "status": "CONFIRMED"},
                take=50,
            )
            corroborations = max(1, len(rows))
        except Exception:
            corroborations = 1

    return {
        "base": _clamp01(fact.confidence_t0),
        "time_decay": _clamp01(time_decay),
        "source_rep": _clamp01(source_rep),
        "corroborations": float(min(20, corroborations)) / 20.0,
    }


# ─────────────────────────────────────────────────────────────
# 부트스트랩
# ─────────────────────────────────────────────────────────────
async def _bootstrap_confidence(
    fact: KnowledgeFact, n_iter: int, confidence_level: float
) -> tuple[float, float]:
    """품질 지표를 재표본추출 → percentile 기반 CI."""
    sig = await _quality_signals(fact)
    values = list(sig.values())
    if not values:
        return (fact.confidence_t0, fact.confidence_t0)

    samples: list[float] = []
    rng = random.Random(42)
    for _ in range(max(100, n_iter)):
        # 복원추출
        resampled = [rng.choice(values) for _ in range(len(values))]
        # 결합 점수: 가중 평균
        combined = sum(resampled) / len(resampled)
        samples.append(_clamp01(combined))

    lo_q = (1 - confidence_level) / 2 * 100
    hi_q = 100 - lo_q
    return (_percentile(samples, lo_q), _percentile(samples, hi_q))


# ─────────────────────────────────────────────────────────────
# 베이지안
# ─────────────────────────────────────────────────────────────
async def _bayesian_confidence(
    fact: KnowledgeFact, confidence_level: float
) -> tuple[float, float]:
    """Beta(α, β) posterior 의 credible interval.

    지지 = 독립 출처 corroborations + reputation 기반 pseudo-count
    반박 = 같은 entity 에 대한 모순(contradictions) 수
    """
    alpha_prior, beta_prior = 2.0, 2.0   # weak uninformative

    supports = 0
    opposes = 0
    if fact.entity:
        try:
            supports_rows = await prisma.knowledgefact.find_many(
                where={"entity": fact.entity, "status": "CONFIRMED"},
                take=100,
            )
            supports = max(0, len(supports_rows) - 1)
        except Exception:
            supports = 0
        try:
            retracted_rows = await prisma.knowledgefact.find_many(
                where={"entity": fact.entity, "status": "RETRACTED"},
                take=100,
            )
            opposes = len(retracted_rows)
        except Exception:
            opposes = 0

    try:
        rep = await get_reputation(fact.source)
    except Exception:
        rep = 0.5
    # 평판을 pseudo-count 로 변환 (0~5)
    pseudo = round(rep * 5)

    alpha = alpha_prior + supports + pseudo
    beta = beta_prior + opposes

    lo_q = (1 - confidence_level) / 2
    hi_q = 1 - lo_q
    return (beta_quantile(alpha, beta, lo_q), beta_quantile(alpha, beta, hi_q))


# ─────────────────────────────────────────────────────────────
# 몬테카를로
# ─────────────────────────────────────────────────────────────
async def _monte_carlo_confidence(
    fact: KnowledgeFact, n_iter: int, confidence_level: float
) -> tuple[float, float]:
    """파라미터에 가우시안 노이즈를 가해 arbitrated_confidence 반복 계산."""
    samples: list[float] = []
    rng = random.Random(7)
    base_fact_dict = fact.model_dump()

    # 반복 비용이 크므로 합리적 상한
    iters = min(max(20, n_iter), 200)
    for _ in range(iters):
        perturbed = base_fact_dict.copy()
        # confidence_t0 에 노이즈
        noise = rng.gauss(0.0, 0.05)
        perturbed["confidence_t0"] = _clamp01(float(perturbed.get("confidence_t0", 1.0)) + noise)
        try:
            pert = KnowledgeFact(**perturbed)
            res = await arbitrated_confidence(pert)
            samples.append(_clamp01(float(res.get("score", 0.0))))
        except Exception as exc:
            logger.debug("monte_carlo iter failed: %s", exc)
            continue

    if not samples:
        return (fact.confidence_t0, fact.confidence_t0)

    lo_q = (1 - confidence_level) / 2 * 100
    hi_q = 100 - lo_q
    return (_percentile(samples, lo_q), _percentile(samples, hi_q))


# ─────────────────────────────────────────────────────────────
# 앙상블
# ─────────────────────────────────────────────────────────────
async def _ensemble_confidence(
    fact: KnowledgeFact, confidence_level: float
) -> tuple[float, float]:
    """여러 방법의 결과를 종합 — median ± 1.96·σ (95%)."""
    boots = await _bootstrap_confidence(fact, 500, confidence_level)
    bayes = await _bayesian_confidence(fact, confidence_level)
    mc = await _monte_carlo_confidence(fact, 50, confidence_level)

    lows = [boots[0], bayes[0], mc[0]]
    highs = [boots[1], bayes[1], mc[1]]
    center = median(lows + highs)
    sd = std_from_samples(lows + highs)
    z = 1.96 if abs(confidence_level - 0.95) < 1e-6 else 1.64
    return (_clamp01(center - z * sd), _clamp01(center + z * sd))


# ─────────────────────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────────────────────
async def compute_confidence_interval(
    fact: KnowledgeFact,
    method: str = "bootstrap",
    n_iter: int = 1000,
    confidence_level: float = 0.95,
) -> dict:
    """지정 방법으로 신뢰 구간 계산.

    반환::

        {
          "lower": float,
          "upper": float,
          "point_estimate": float,
          "method": str,
          "width": float,
          "sample_size": int,
        }
    """
    m = method.lower()
    if m == "bootstrap":
        lo, hi = await _bootstrap_confidence(fact, n_iter, confidence_level)
    elif m == "bayesian":
        lo, hi = await _bayesian_confidence(fact, confidence_level)
    elif m == "monte_carlo":
        lo, hi = await _monte_carlo_confidence(fact, n_iter, confidence_level)
    elif m == "ensemble":
        lo, hi = await _ensemble_confidence(fact, confidence_level)
    else:
        raise ValueError(f"unknown method: {method}")

    lo, hi = _clamp01(lo), _clamp01(hi)
    if lo > hi:
        lo, hi = hi, lo

    # point estimate 로는 arbitrated_confidence 결과 사용
    try:
        arb = await arbitrated_confidence(fact)
        point = float(arb.get("score", (lo + hi) / 2.0))
    except Exception:
        point = (lo + hi) / 2.0

    return {
        "lower": round(lo, 4),
        "upper": round(hi, 4),
        "point_estimate": round(_clamp01(point), 4),
        "method": m,
        "width": round(hi - lo, 4),
        "sample_size": n_iter,
        "confidence_level": confidence_level,
    }


# ─────────────────────────────────────────────────────────────
# DB 반영
# ─────────────────────────────────────────────────────────────
def _row_to_fact(row: Any) -> KnowledgeFact:
    from datetime import datetime, timezone

    return KnowledgeFact(
        id=row.id,
        content=row.content,
        domain=row.domain,
        entity=row.entity,
        tags=list(row.tags or []),
        language=row.language,
        valid_from=row.validFrom,
        valid_to=getattr(row, "validTo", None),
        created_at=getattr(row, "createdAt", None),
        last_verified_at=getattr(row, "lastVerifiedAt", None),
        confidence_t0=float(row.confidenceT0),
        half_life_days=getattr(row, "halfLifeDays", None),
        status=KnowledgeStatus(row.status),
        source=row.source,
        source_url=getattr(row, "sourceUrl", None),
    )


async def apply_uncertainty_to_fact(
    fact_id: str, method: str = "bootstrap"
) -> dict:
    """DB 의 confidenceInterval/uncertaintyMethod/credibleIntervalWidth 를 업데이트."""
    try:
        row = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    except Exception as exc:
        logger.warning("apply_uncertainty lookup failed: %s", exc)
        return {"error": "lookup_failed"}
    if row is None:
        return {"error": "not_found"}

    fact = _row_to_fact(row)
    ci = await compute_confidence_interval(fact, method=method)

    interval_json = {
        "lower": ci["lower"],
        "upper": ci["upper"],
        "method": ci["method"],
    }
    try:
        await prisma.knowledgefact.update(
            where={"id": fact_id},
            data={
                "confidenceInterval": interval_json,
                "uncertaintyMethod": ci["method"],
                "credibleIntervalWidth": ci["width"],
            },
        )
    except Exception as exc:
        logger.debug("apply_uncertainty persist skipped: %s", exc)

    return {"fact_id": fact_id, **ci}


async def batch_apply_uncertainty(
    domain: str | None = None,
    method: str = "bootstrap",
    limit: int = 200,
) -> dict:
    """도메인 단위로 일괄 업데이트."""
    where: dict[str, Any] = {"status": "CONFIRMED"}
    if domain:
        where["domain"] = domain
    try:
        rows = await prisma.knowledgefact.find_many(
            where=where, take=limit, order={"lastVerifiedAt": "desc"},
        )
    except Exception as exc:
        logger.warning("batch_apply_uncertainty find failed: %s", exc)
        return {"processed": 0, "updated": 0, "failed": 0}

    processed = 0
    updated = 0
    failed = 0
    widths: list[float] = []
    for r in rows:
        processed += 1
        try:
            result = await apply_uncertainty_to_fact(r.id, method=method)
            if "error" in result:
                failed += 1
                continue
            widths.append(float(result.get("width", 0.0)))
            updated += 1
        except Exception as exc:
            logger.warning("batch item %s failed: %s", r.id, exc)
            failed += 1

    avg_width = mean(widths) if widths else 0.0
    return {
        "processed": processed,
        "updated": updated,
        "failed": failed,
        "avg_width": round(avg_width, 4),
        "domain": domain,
        "method": method,
    }


# ─────────────────────────────────────────────────────────────
# 포맷 / 판정
# ─────────────────────────────────────────────────────────────
def format_interval(ci: dict, display_mode: str = "text") -> str:
    """``0.72 [0.65~0.79]`` 형식의 한국어 표현."""
    lo = float(ci.get("lower", 0.0))
    hi = float(ci.get("upper", 0.0))
    point = float(ci.get("point_estimate", (lo + hi) / 2.0))
    verdict = interval_to_verdict(ci)
    if display_mode == "markdown":
        return f"**{point:.2f}** `[{lo:.2f}~{hi:.2f}]` — {verdict}"
    if display_mode == "short":
        return f"{point:.2f}±{((hi - lo) / 2):.2f}"
    return f"{point:.2f} [{lo:.2f}~{hi:.2f}] ({verdict})"


def interval_to_verdict(ci: dict) -> str:
    """구간 폭 → 한국어 확신 수준."""
    width = float(ci.get("width", abs(float(ci.get("upper", 0)) - float(ci.get("lower", 0)))))
    if width < 0.1:
        return "확실"
    if width < 0.2:
        return "비교적 확실"
    if width < 0.3:
        return "중간 확신"
    if width < 0.5:
        return "불확실"
    return "매우 불확실"


# ─────────────────────────────────────────────────────────────
# 캘리브레이션 체크
# ─────────────────────────────────────────────────────────────
async def calibration_check(domain: str, last_days: int = 30) -> dict:
    """예측 신뢰도 bin 과 실제 정확도 bin 을 비교하여 calibration error 계산.

    예: 0.8 대 사실 중 80% 가 여전히 유효 (not retracted / not expired) 해야 이상적.
    """
    from datetime import datetime, timedelta, timezone

    since = datetime.now(timezone.utc) - timedelta(days=last_days)
    try:
        rows = await prisma.knowledgefact.find_many(
            where={
                "domain": domain,
                "lastVerifiedAt": {"gte": since},
            },
            take=2000,
        )
    except Exception as exc:
        logger.warning("calibration_check fetch failed: %s", exc)
        return {"error": "fetch_failed"}

    if not rows:
        return {"domain": domain, "sample": 0, "calibration_error": 0.0}

    # bin 정의: 0.0~1.0 을 10개 구간
    bins = [(i / 10.0, (i + 1) / 10.0) for i in range(10)]
    predicted_counts = [0] * 10
    correct_counts = [0] * 10

    for r in rows:
        conf = float(getattr(r, "arbitratedScore", None) or r.confidenceT0 or 0.0)
        idx = min(9, max(0, int(conf * 10)))
        predicted_counts[idx] += 1
        # "맞춘" 기준: status 가 CONFIRMED 유지 = 맞음, RETRACTED/EXPIRED = 틀림
        if str(r.status) == "CONFIRMED":
            correct_counts[idx] += 1

    predicted_bins: list[dict] = []
    actual_bins: list[dict] = []
    total_error = 0.0
    total_samples = 0
    for i, (lo, hi) in enumerate(bins):
        n = predicted_counts[i]
        if n == 0:
            continue
        expected = (lo + hi) / 2.0
        actual = correct_counts[i] / n
        predicted_bins.append({"bin": [lo, hi], "count": n, "expected_accuracy": expected})
        actual_bins.append({"bin": [lo, hi], "count": n, "actual_accuracy": round(actual, 4)})
        total_error += abs(expected - actual) * n
        total_samples += n

    calibration_error = (total_error / total_samples) if total_samples else 0.0

    # 과신/저신 경향
    tendency = "balanced"
    over = under = 0
    for p, a in zip(predicted_bins, actual_bins):
        if p["expected_accuracy"] > a["actual_accuracy"] + 0.05:
            over += p["count"]
        elif p["expected_accuracy"] < a["actual_accuracy"] - 0.05:
            under += p["count"]
    if over > under * 1.3:
        tendency = "overconfident"
    elif under > over * 1.3:
        tendency = "underconfident"

    return {
        "domain": domain,
        "sample": total_samples,
        "predicted_confidence_bins": predicted_bins,
        "actual_accuracy_bins": actual_bins,
        "calibration_error": round(calibration_error, 4),
        "tendency": tendency,
        "last_days": last_days,
    }


__all__ = [
    "compute_confidence_interval",
    "apply_uncertainty_to_fact",
    "batch_apply_uncertainty",
    "format_interval",
    "interval_to_verdict",
    "calibration_check",
    "beta_quantile",
    "std_from_samples",
]
