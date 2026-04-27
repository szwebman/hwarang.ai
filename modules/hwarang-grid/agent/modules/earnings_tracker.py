"""에이전트 수익 추적 — 마스터에서 지급 내역 조회 + 월 수익 예측.

역할:
  - 나의 HWARANG 보상/슬래시 내역을 마스터에서 주기적으로 동기화.
  - 도메인별·라운드별 분포 요약.
  - 지난 30일 데이터를 기반으로 월 수익 예측 (GPU/가동시간 반영).
  - 터미널 대시보드 출력 + CSV 내보내기 (세금 신고용).

보안/투명성:
  - API 키 기반 조회만 수행 (쓰기 없음).
  - 마스터가 제공하는 숫자를 그대로 쓰되, slash 를 양수로 기록해
    마이너스 실수를 방지.
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# GPU 성능 테이블 (reward_verifier.py 와 일치시킬 계수)
# -----------------------------------------------------------------------------

_GPU_MULTIPLIER: dict[str, float] = {
    "H100":       3.0,
    "A100_80G":   2.2,
    "A100_40G":   2.0,
    "RTX_5090":   1.6,
    "RTX_4090":   1.0,  # 기준
    "RTX_4080":   0.8,
    "RTX_3090":   0.75,
    "RTX_3080":   0.55,
    "RTX_3060":   0.35,
    "RTX_2080":   0.3,
    "M3_MAX":     0.45,
    "M2_ULTRA":   0.6,
    "CPU_ONLY":   0.05,
}

# 한국 전기 요금 (주택용 2단계 기준, KRW/kWh) — 대략치
_ELEC_KRW_PER_KWH = 280

_GPU_WATTS: dict[str, int] = {
    "H100":     700, "A100_80G": 400, "A100_40G": 400,
    "RTX_5090": 575, "RTX_4090": 450, "RTX_4080": 320,
    "RTX_3090": 350, "RTX_3080": 320, "RTX_3060": 170,
    "RTX_2080": 215, "M3_MAX":   80,  "M2_ULTRA": 120,
    "CPU_ONLY": 65,
}


# -----------------------------------------------------------------------------
# Dataclass
# -----------------------------------------------------------------------------


@dataclass
class EarningsRecord:
    """한 라운드에서 받은 수익 내역."""

    round_id: str
    round_name: str
    domain: str
    joined_at: datetime
    completed_at: datetime | None = None
    reward: int = 0
    slashed: int = 0
    rank_in_round: int | None = None
    contribution_score: float = 0.0
    peer_vote_received: float | None = None
    status: str = "pending"  # 'completed', 'rejected', 'slashed', 'pending'

    @property
    def net(self) -> int:
        return self.reward - self.slashed

    def to_dict(self) -> dict:
        return {
            "round_id": self.round_id,
            "round_name": self.round_name,
            "domain": self.domain,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "reward": self.reward,
            "slashed": self.slashed,
            "net": self.net,
            "rank_in_round": self.rank_in_round,
            "contribution_score": self.contribution_score,
            "peer_vote_received": self.peer_vote_received,
            "status": self.status,
        }


# -----------------------------------------------------------------------------
# 내부 유틸
# -----------------------------------------------------------------------------


def _parse_dt(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, tz=timezone.utc)
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def _record_from_raw(raw: dict) -> EarningsRecord:
    return EarningsRecord(
        round_id=str(raw.get("round_id") or raw.get("id") or ""),
        round_name=str(raw.get("round_name") or raw.get("name") or ""),
        domain=str(raw.get("domain") or "general"),
        joined_at=_parse_dt(raw.get("joined_at")) or datetime.now(timezone.utc),
        completed_at=_parse_dt(raw.get("completed_at")),
        reward=int(raw.get("reward") or 0),
        slashed=abs(int(raw.get("slashed") or 0)),
        rank_in_round=raw.get("rank_in_round"),
        contribution_score=float(raw.get("contribution_score") or 0.0),
        peer_vote_received=raw.get("peer_vote_received"),
        status=str(raw.get("status") or "pending"),
    )


def gpu_performance_multiplier(gpu_name: str) -> float:
    """GPU 성능 계수 (reward_verifier.py 와 일관)."""
    if not gpu_name:
        return 1.0
    key = gpu_name.upper().replace(" ", "_").replace("-", "_")
    # 약어 매칭
    for k, v in _GPU_MULTIPLIER.items():
        if k in key or key in k:
            return v
    return 1.0


def _gpu_watts(gpu_name: str) -> int:
    if not gpu_name:
        return 450
    key = gpu_name.upper().replace(" ", "_").replace("-", "_")
    for k, v in _GPU_WATTS.items():
        if k in key or key in k:
            return v
    return 450


# -----------------------------------------------------------------------------
# HTTP: 마스터 조회
# -----------------------------------------------------------------------------


async def fetch_earnings(
    master_url: str,
    agent_id: str,
    api_key: str,
    since: datetime | None = None,
    max_retries: int = 3,
) -> list[EarningsRecord]:
    """GET /api/grid/agents/{agent_id}/earnings?since=...

    네트워크 일시 장애 대응: 5xx/네트워크 오류 시 최대 3회 재시도
    (1s, 2s, 4s exponential backoff). 4xx 는 즉시 빈 결과.
    """
    if httpx is None:
        logger.warning("httpx 미설치 — 수익 조회 불가")
        return []

    url = f"{master_url.rstrip('/')}/api/grid/agents/{agent_id}/earnings"
    params = {}
    if since:
        params["since"] = since.isoformat()
    headers = {"Authorization": f"Bearer {api_key}"}

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, params=params, headers=headers)
                if 400 <= resp.status_code < 500:
                    logger.error("수익 조회 클라이언트 오류 %d", resp.status_code)
                    return []
                resp.raise_for_status()
                data = resp.json()
                items = data if isinstance(data, list) else data.get("records", [])
                return [_record_from_raw(r) for r in items]
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                await asyncio.sleep(2**attempt)

    logger.error("수익 조회 실패 (재시도 %d회): %s", max_retries, last_exc)
    return []


async def earnings_summary(
    master_url: str,
    agent_id: str,
    api_key: str,
    days: int = 30,
) -> dict:
    """총 수익/슬래시/라운드 수/도메인 분포."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    records = await fetch_earnings(master_url, agent_id, api_key, since)

    total_reward = sum(r.reward for r in records)
    total_slash = sum(r.slashed for r in records)
    by_domain: dict[str, int] = {}
    by_status: dict[str, int] = {}
    ranks: list[int] = []

    for r in records:
        by_domain[r.domain] = by_domain.get(r.domain, 0) + r.reward
        by_status[r.status] = by_status.get(r.status, 0) + 1
        if r.rank_in_round is not None:
            ranks.append(r.rank_in_round)

    return {
        "agent_id": agent_id,
        "period_days": days,
        "total_rounds": len(records),
        "total_reward": total_reward,
        "total_slash": total_slash,
        "net": total_reward - total_slash,
        "average_rank": round(sum(ranks) / len(ranks), 2) if ranks else None,
        "by_domain": dict(sorted(by_domain.items(), key=lambda x: -x[1])),
        "by_status": by_status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def check_unpaid_rewards(
    master_url: str,
    agent_id: str,
    api_key: str,
) -> list[dict]:
    """지급 지연 보상 체크 (문제 감지).

    - status == 'pending' + completed_at 이 48h 이상 지난 것.
    """
    records = await fetch_earnings(master_url, agent_id, api_key)
    now = datetime.now(timezone.utc)
    unpaid: list[dict] = []
    for r in records:
        if r.status != "pending":
            continue
        if r.completed_at is None:
            continue
        age_h = (now - r.completed_at).total_seconds() / 3600
        if age_h >= 48:
            unpaid.append({
                "round_id": r.round_id,
                "round_name": r.round_name,
                "expected_reward": r.reward,
                "hours_overdue": round(age_h - 48, 1),
                "completed_at": r.completed_at.isoformat(),
            })
    return unpaid


# -----------------------------------------------------------------------------
# 월 수익 예측
# -----------------------------------------------------------------------------


async def forecast_monthly_earnings(
    master_url: str,
    agent_id: str,
    api_key: str,
    past_days: int = 30,
    gpu_tier: str = "RTX_4090",
    hours_per_day: float = 8.0,
) -> dict:
    """지난 과거 × 예상 가동 시간 × GPU 성능 배수로 월 수익 예측.

    Return:
        {
            "estimated_monthly_reward": 12450,
            "estimated_monthly_slash": 150,
            "estimated_power_cost_krw": 3500,
            "estimated_net_profit_krw": ...,
            "breakeven_hours": ...,
            "by_domain": {"law": 8500, "general": 4000},
            "confidence": 0.7
        }
    """
    since = datetime.now(timezone.utc) - timedelta(days=past_days)
    records = await fetch_earnings(master_url, agent_id, api_key, since)

    if not records:
        return {
            "estimated_monthly_reward": 0,
            "estimated_monthly_slash": 0,
            "estimated_power_cost_krw": 0,
            "estimated_net_profit_krw": 0,
            "breakeven_hours": None,
            "by_domain": {},
            "confidence": 0.0,
            "note": "no historical data",
        }

    # 일당 평균 → 30일 환산
    daily_reward = sum(r.reward for r in records) / max(1, past_days)
    daily_slash = sum(r.slashed for r in records) / max(1, past_days)

    gpu_mult = gpu_performance_multiplier(gpu_tier)
    hours_ratio = hours_per_day / 8.0  # 기준 8h

    monthly_reward = int(daily_reward * 30 * gpu_mult * hours_ratio)
    monthly_slash = int(daily_slash * 30 * gpu_mult * hours_ratio)

    # 전기 요금
    watts = _gpu_watts(gpu_tier)
    kwh = watts / 1000.0 * hours_per_day * 30
    power_krw = int(kwh * _ELEC_KRW_PER_KWH)

    # 1 HWARANG == 100 KRW 가정치 (실제는 마스터에서 조회해야 함, 없으면 상수)
    reward_krw = monthly_reward * 100
    slash_krw = monthly_slash * 100
    net_krw = reward_krw - slash_krw - power_krw

    # breakeven: 한 시간당 수익이 전기료를 넘는지
    per_hour_reward_krw = (monthly_reward * 100) / max(1, hours_per_day * 30)
    per_hour_power_krw = watts / 1000.0 * _ELEC_KRW_PER_KWH
    if per_hour_reward_krw > 0:
        breakeven = round(per_hour_power_krw / per_hour_reward_krw * hours_per_day, 1)
    else:
        breakeven = None

    by_domain: dict[str, int] = {}
    for r in records:
        by_domain[r.domain] = by_domain.get(r.domain, 0) + r.reward
    by_domain_scaled = {
        k: int(v / max(1, past_days) * 30 * gpu_mult * hours_ratio)
        for k, v in by_domain.items()
    }

    # 신뢰도: 라운드 수 기반
    confidence = max(0.0, min(1.0, len(records) / 30))

    return {
        "estimated_monthly_reward": monthly_reward,
        "estimated_monthly_slash": monthly_slash,
        "estimated_power_cost_krw": power_krw,
        "estimated_reward_krw": reward_krw,
        "estimated_net_profit_krw": net_krw,
        "breakeven_hours": breakeven,
        "by_domain": dict(sorted(by_domain_scaled.items(), key=lambda x: -x[1])),
        "gpu_tier": gpu_tier,
        "gpu_multiplier": gpu_mult,
        "hours_per_day": hours_per_day,
        "confidence": round(confidence, 2),
        "sample_rounds": len(records),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# -----------------------------------------------------------------------------
# Export & Dashboard
# -----------------------------------------------------------------------------


async def export_earnings_csv(
    master_url: str,
    agent_id: str,
    api_key: str,
    output_path: str,
    since: datetime | None = None,
) -> int:
    """수익 내역 CSV 로 (세금 신고용)."""
    records = await fetch_earnings(master_url, agent_id, api_key, since)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "round_id", "round_name", "domain",
        "joined_at", "completed_at",
        "reward", "slashed", "net",
        "rank_in_round", "contribution_score",
        "peer_vote_received", "status",
    ]
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in records:
            row = r.to_dict()
            writer.writerow({k: row.get(k, "") for k in fields})
    return len(records)


def _format_krw(n: int) -> str:
    return f"{n:,}"


async def show_earnings_dashboard(
    master_url: str,
    agent_id: str,
    api_key: str,
) -> str:
    """터미널용 대시보드 문자열 생성."""
    summary = await earnings_summary(master_url, agent_id, api_key, days=30)
    forecast = await forecast_monthly_earnings(master_url, agent_id, api_key)
    unpaid = await check_unpaid_rewards(master_url, agent_id, api_key)

    lines: list[str] = []
    bar = "=" * 55
    lines.append(bar)
    lines.append(f"  에이전트: {agent_id}")
    lines.append(f"  총 수익: {_format_krw(summary['total_reward'])} HWARANG")
    lines.append(f"  슬래시:  {_format_krw(summary['total_slash'])} HWARANG")
    lines.append(f"  순수익:  {_format_krw(summary['net'])} HWARANG")
    lines.append(bar)

    lines.append("최근 30일 활동:")
    lines.append(f"  - 참여 라운드: {summary['total_rounds']}")
    if summary.get("average_rank") is not None:
        lines.append(f"  - 평균 순위:   {summary['average_rank']}")
    lines.append("")

    if summary["by_domain"]:
        lines.append("도메인 분포:")
        total = max(1, summary["total_reward"])
        for dom, amt in summary["by_domain"].items():
            pct = (amt / total) * 100
            lines.append(f"  {dom:12s} {_format_krw(amt):>10s}  ({pct:5.1f}%)")
        lines.append("")

    lines.append("예상 월 수익:")
    lines.append(f"  - 보상 (토큰): {_format_krw(forecast['estimated_monthly_reward'])} HWARANG")
    lines.append(f"  - 보상 (원화): {_format_krw(forecast.get('estimated_reward_krw', 0))} KRW")
    lines.append(f"  - 전기료 추정: {_format_krw(forecast['estimated_power_cost_krw'])} KRW")
    lines.append(f"  - 순이익:     {_format_krw(forecast['estimated_net_profit_krw'])} KRW")
    lines.append(f"  - 신뢰도:     {forecast['confidence']} (샘플 {forecast['sample_rounds']}건)")
    lines.append("")

    if unpaid:
        lines.append(f"[!] 지급 지연 의심: {len(unpaid)} 건")
        for u in unpaid[:5]:
            lines.append(f"    · {u['round_name']} — {u['hours_overdue']}h 초과")
    lines.append(bar)
    return "\n".join(lines)


__all__ = [
    "EarningsRecord",
    "fetch_earnings",
    "earnings_summary",
    "forecast_monthly_earnings",
    "export_earnings_csv",
    "gpu_performance_multiplier",
    "show_earnings_dashboard",
    "check_unpaid_rewards",
]
