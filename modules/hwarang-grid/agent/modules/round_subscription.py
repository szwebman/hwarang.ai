"""라운드 구독/필터

마스터가 공지한 라운드 목록을 받아 내 조건으로 필터링한다.

책임 분리:
    - round_subscription.py (이 파일): 발견/평가/판단
    - participation_control.py       : 실제 join/decline/heartbeat

에이전트는 PARTICIPANT. 라운드를 만들지 않고 받기만 한다.
폴링(HTTP) 또는 WebSocket 두 모드 지원 — 마스터 엔드포인트는 /api/grid/* 로 통일.

의사결정 흐름:
    1. list_available_rounds()  → 열린 라운드 조회
    2. evaluate_round()          → domain + VRAM + 전기세 + ROI 점수화
    3. should_accept()           → 최종 yes/no
    4. on_eligible_round 콜백    → participation_control.join_round()
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

try:
    import httpx  # type: ignore
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

from .domain_specialization import (
    DomainProfile,
    is_active_now,
    match_round_to_profile,
)

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# 상수
# ----------------------------------------------------------------------------

# 한전 주택용 일반 기준 대략치 (실제 요금제에 따라 다름)
DEFAULT_KRW_PER_KWH: float = 150.0
# 심야 할인 시간대 (23:00~09:00) 대략 60원
NIGHT_KRW_PER_KWH: float = 60.0


# ----------------------------------------------------------------------------
# Dataclass
# ----------------------------------------------------------------------------


@dataclass
class RoundMeta:
    """마스터가 공지하는 라운드 메타데이터."""

    round_id: str
    round_name: str
    domain: str
    model_base: str
    data_samples: int
    lora_r: int
    epochs: int
    estimated_time_minutes: int
    estimated_reward: int  # HWARANG 코인
    min_tier_required: str  # "BRONZE" | "SILVER" | "GOLD" | "PLATINUM"
    min_vram_gb: int
    starts_at: datetime
    deadline: datetime
    # 선택 필드
    data_tier: str = "GENERAL_MEDIA"
    language: str = "ko"
    max_participants: int | None = None
    current_participants: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RoundMeta":
        """서버 응답 dict → RoundMeta (datetime 파싱 포함)."""
        def _parse_dt(v: Any) -> datetime:
            if isinstance(v, datetime):
                return v
            if isinstance(v, str):
                try:
                    return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except ValueError:
                    pass
            return datetime.now(timezone.utc)

        known = set(cls.__dataclass_fields__.keys())
        mapped = {k: v for k, v in data.items() if k in known}
        extras = {k: v for k, v in data.items() if k not in known}

        mapped["starts_at"] = _parse_dt(mapped.get("starts_at"))
        mapped["deadline"] = _parse_dt(mapped.get("deadline"))
        if extras:
            mapped["extra"] = extras
        return cls(**mapped)


# ----------------------------------------------------------------------------
# 조회
# ----------------------------------------------------------------------------


async def list_available_rounds(
    master_url: str,
    agent_id: str,
    api_key: str,
    domain_filter: list[str] | None = None,
    timeout: float = 10.0,
) -> list[RoundMeta]:
    """GET /api/grid/rounds/open?agent_id=...&domain=...

    오픈된 라운드 목록을 마스터에서 조회.
    """
    if httpx is None:
        logger.warning("httpx 미설치 — list_available_rounds 스킵")
        return []

    url = f"{master_url.rstrip('/')}/api/grid/rounds/open"
    params: dict[str, Any] = {"agent_id": agent_id}
    if domain_filter:
        params["domain"] = ",".join(domain_filter)

    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as e:
        logger.error("라운드 조회 실패: %s", e)
        return []

    rounds_raw = payload.get("rounds", payload) if isinstance(payload, dict) else payload
    rounds: list[RoundMeta] = []
    for r in rounds_raw or []:
        try:
            rounds.append(RoundMeta.from_dict(r))
        except Exception as e:
            logger.warning("라운드 파싱 실패, 스킵: %s", e)
    logger.info("라운드 %d건 수신", len(rounds))
    return rounds


# ----------------------------------------------------------------------------
# 전기세 추정
# ----------------------------------------------------------------------------


def estimate_power_cost(
    gpu_watt: int,
    duration_minutes: int,
    krw_per_kwh: float = DEFAULT_KRW_PER_KWH,
) -> float:
    """전기세 추정 (원).

    공식: (W × h) / 1000 × krw_per_kwh
    """
    hours = duration_minutes / 60.0
    kwh = (gpu_watt * hours) / 1000.0
    return round(kwh * krw_per_kwh, 2)


def _is_night_hour(now: datetime | None = None) -> bool:
    now = now or datetime.now()
    h = now.hour
    return h >= 23 or h < 9


def estimate_power_cost_auto(
    gpu_watt: int,
    duration_minutes: int,
    now: datetime | None = None,
) -> float:
    """시간대별 단가 자동 선택."""
    rate = NIGHT_KRW_PER_KWH if _is_night_hour(now) else DEFAULT_KRW_PER_KWH
    return estimate_power_cost(gpu_watt, duration_minutes, rate)


# ----------------------------------------------------------------------------
# 등급 체크
# ----------------------------------------------------------------------------

TIER_ORDER: list[str] = ["BRONZE", "SILVER", "GOLD", "PLATINUM", "DIAMOND"]


def _tier_rank(tier: str) -> int:
    try:
        return TIER_ORDER.index(tier.upper())
    except ValueError:
        return -1


def _meets_tier(my_tier: str, required: str) -> bool:
    return _tier_rank(my_tier) >= _tier_rank(required)


# ----------------------------------------------------------------------------
# 평가
# ----------------------------------------------------------------------------


async def evaluate_round(
    round_meta: RoundMeta,
    profile: DomainProfile,
    current_gpu_vram_gb: int,
    current_load: float,
    my_tier: str = "BRONZE",
    gpu_watt: int = 250,
) -> dict[str, Any]:
    """라운드 참여 적합성 판단.

    Args:
        round_meta: 라운드 메타
        profile: 내 DomainProfile
        current_gpu_vram_gb: 내 GPU 여유 VRAM (GB)
        current_load: 현재 GPU 부하 (0~1)
        my_tier: 내 평판 등급
        gpu_watt: 내 GPU 평균 소비전력 (W)

    Returns:
        {
            "should_join": bool,
            "match_score": 0~1,
            "eligible": bool,
            "estimated_reward": int,
            "estimated_power_cost_krw": float,
            "expected_roi": float,
            "reasons": [...],
            "decision": "auto_join" | "manual_review" | "decline",
        }
    """
    reasons: list[str] = []

    # 1. 도메인 매칭
    m = match_round_to_profile(asdict_round(round_meta), profile)
    match_score: float = m["match_score"]
    reasons.extend(m["reasons"])
    if not m["is_eligible"]:
        return _decline(match_score, reasons, round_meta.estimated_reward)

    # 2. VRAM 체크
    if current_gpu_vram_gb < round_meta.min_vram_gb:
        reasons.append(
            f"VRAM 부족 (요구 {round_meta.min_vram_gb}GB, 내 {current_gpu_vram_gb}GB)"
        )
        return _decline(match_score, reasons, round_meta.estimated_reward, eligible=False)

    # 3. 등급 체크
    if not _meets_tier(my_tier, round_meta.min_tier_required):
        reasons.append(
            f"등급 미달 (요구 {round_meta.min_tier_required}, 내 {my_tier})"
        )
        return _decline(match_score, reasons, round_meta.estimated_reward, eligible=False)

    # 4. 참가자 정원
    if round_meta.max_participants is not None:
        if round_meta.current_participants >= round_meta.max_participants:
            reasons.append("정원 초과")
            return _decline(match_score, reasons, round_meta.estimated_reward, eligible=False)

    # 5. 현재 부하
    if current_load > 0.8:
        reasons.append(f"현재 GPU 부하 높음 ({current_load:.0%}) — 보류 권장")

    # 6. 전기세 & ROI
    power_cost = estimate_power_cost_auto(gpu_watt, round_meta.estimated_time_minutes)
    # 편의상 1 HWARANG = 100원 가정 (실제는 서버 시세 사용 필요)
    reward_krw = round_meta.estimated_reward * 100.0
    expected_roi = (reward_krw - power_cost) / max(power_cost, 1.0)
    reasons.append(
        f"보상 {round_meta.estimated_reward}H ≈ {reward_krw:.0f}원, "
        f"전기세 ≈ {power_cost:.0f}원, ROI={expected_roi:.2f}x"
    )

    # 7. 마감 임박도
    now = datetime.now(timezone.utc)
    if round_meta.deadline.tzinfo is None:
        deadline = round_meta.deadline.replace(tzinfo=timezone.utc)
    else:
        deadline = round_meta.deadline
    remaining_min = (deadline - now).total_seconds() / 60
    if remaining_min < round_meta.estimated_time_minutes:
        reasons.append(
            f"마감 임박 — 잔여 {remaining_min:.0f}분 < 필요 {round_meta.estimated_time_minutes}분"
        )
        return _decline(match_score, reasons, round_meta.estimated_reward, eligible=False)

    # 8. 최종 의사결정 힌트
    decision = "auto_join" if (match_score >= 0.7 and expected_roi >= 1.5) else "manual_review"
    if match_score < 0.3 or expected_roi < 0.5:
        decision = "decline"

    return {
        "should_join": decision == "auto_join",
        "match_score": match_score,
        "eligible": True,
        "estimated_reward": round_meta.estimated_reward,
        "estimated_power_cost_krw": power_cost,
        "expected_roi": round(expected_roi, 2),
        "reasons": reasons,
        "decision": decision,
    }


def asdict_round(round_meta: RoundMeta) -> dict[str, Any]:
    """RoundMeta → match_round_to_profile 가 기대하는 dict."""
    return {
        "domain": round_meta.domain,
        "min_tier_required": round_meta.min_tier_required,
        "data_tier": round_meta.data_tier,
        "language": round_meta.language,
    }


def _decline(
    match_score: float,
    reasons: list[str],
    estimated_reward: int,
    eligible: bool = True,
) -> dict[str, Any]:
    return {
        "should_join": False,
        "match_score": match_score,
        "eligible": eligible,
        "estimated_reward": estimated_reward,
        "estimated_power_cost_krw": 0.0,
        "expected_roi": 0.0,
        "reasons": reasons,
        "decision": "decline",
    }


# ----------------------------------------------------------------------------
# 최종 판단
# ----------------------------------------------------------------------------


def should_accept(
    eval_result: dict[str, Any],
    min_roi: float = 1.5,
    min_match_score: float = 0.7,
    auto_participate: bool = True,
) -> bool:
    """evaluate_round 결과를 바탕으로 최종 accept 여부."""
    if not auto_participate:
        return False
    if not eval_result.get("eligible", False):
        return False
    if eval_result.get("match_score", 0) < min_match_score:
        return False
    if eval_result.get("expected_roi", 0) < min_roi:
        return False
    return eval_result.get("decision") == "auto_join"


# ----------------------------------------------------------------------------
# 폴링 루프
# ----------------------------------------------------------------------------


async def auto_participation_loop(
    master_url: str,
    agent_id: str,
    api_key: str,
    profile: DomainProfile,
    on_eligible_round: Callable[[RoundMeta, dict[str, Any]], Awaitable[None] | None],
    poll_interval_seconds: int = 60,
    stop_event: asyncio.Event | None = None,
    get_vram_fn: Callable[[], int] | None = None,
    get_load_fn: Callable[[], float] | None = None,
    get_tier_fn: Callable[[], str] | None = None,
    gpu_watt: int = 250,
) -> None:
    """백그라운드 폴링 루프.

    마스터에서 오픈 라운드 주기 조회 → 평가 → 조건 충족 시 콜백.
    콜백은 participation_control.join_round 호출하도록 연결.
    """
    stop_event = stop_event or asyncio.Event()
    logger.info("auto_participation_loop 시작 (interval=%ds)", poll_interval_seconds)

    while not stop_event.is_set():
        try:
            if not is_active_now(profile):
                logger.debug("비활성 시간대 — 다음 주기")
                await _wait_or_stop(stop_event, poll_interval_seconds)
                continue

            rounds = await list_available_rounds(
                master_url, agent_id, api_key,
                domain_filter=profile.primary_domains or None,
            )
            vram = get_vram_fn() if get_vram_fn else 0
            load = get_load_fn() if get_load_fn else 0.0
            tier = get_tier_fn() if get_tier_fn else "BRONZE"

            for r in rounds:
                ev = await evaluate_round(
                    r, profile,
                    current_gpu_vram_gb=vram,
                    current_load=load,
                    my_tier=tier,
                    gpu_watt=gpu_watt,
                )
                if should_accept(ev, auto_participate=profile.auto_participate):
                    logger.info(
                        "적합 라운드 발견: %s (score=%.2f, ROI=%.2fx)",
                        r.round_id, ev["match_score"], ev["expected_roi"],
                    )
                    result = on_eligible_round(r, ev)
                    if asyncio.iscoroutine(result):
                        await result
                elif ev.get("decision") == "manual_review":
                    logger.info(
                        "수동 검토 필요: %s — %s",
                        r.round_id, "; ".join(ev["reasons"]),
                    )
        except Exception as e:
            logger.exception("폴링 루프 오류: %s", e)

        await _wait_or_stop(stop_event, poll_interval_seconds)

    logger.info("auto_participation_loop 종료")


async def _wait_or_stop(stop_event: asyncio.Event, seconds: int) -> None:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        return


# ----------------------------------------------------------------------------
# WebSocket 구독 (선택)
# ----------------------------------------------------------------------------


async def subscribe_websocket(
    master_ws_url: str,
    agent_id: str,
    api_key: str,
    profile: DomainProfile,
    on_round_announced: Callable[[RoundMeta], Awaitable[None] | None],
    stop_event: asyncio.Event | None = None,
) -> None:
    """WebSocket 기반 라운드 공지 구독 (저지연 대안).

    메시지 포맷: {"type": "round_announced", "round": {...}}
    httpx 또는 websockets 패키지 필요.
    """
    stop_event = stop_event or asyncio.Event()
    try:
        import websockets  # type: ignore
    except ImportError:
        logger.warning("websockets 미설치 — WebSocket 구독 스킵, 폴링 사용 권장")
        return

    url = f"{master_ws_url.rstrip('/')}/api/grid/ws/rounds?agent_id={agent_id}"
    headers = [("Authorization", f"Bearer {api_key}")]

    while not stop_event.is_set():
        try:
            async with websockets.connect(url, additional_headers=headers) as ws:
                logger.info("WebSocket 연결 성공: %s", url)
                async for message in ws:
                    if stop_event.is_set():
                        break
                    try:
                        import json as _json
                        data = _json.loads(message)
                    except Exception:
                        continue
                    if data.get("type") != "round_announced":
                        continue
                    try:
                        r = RoundMeta.from_dict(data.get("round", {}))
                    except Exception:
                        continue
                    result = on_round_announced(r)
                    if asyncio.iscoroutine(result):
                        await result
        except Exception as e:
            logger.warning("WebSocket 오류, 재연결 대기: %s", e)
            await _wait_or_stop(stop_event, 10)


# ----------------------------------------------------------------------------
# CLI 테스트
# ----------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")

    from .domain_specialization import apply_preset

    prof = apply_preset("law_specialist")
    prof.owner_expert_credentials = ["BAR_KR:12345"]

    # 가짜 라운드
    r = RoundMeta(
        round_id="r-0001",
        round_name="형사 판례 학습",
        domain="law:criminal",
        model_base="qwen2.5-7b",
        data_samples=10000,
        lora_r=16,
        epochs=3,
        estimated_time_minutes=45,
        estimated_reward=150,
        min_tier_required="BRONZE",
        min_vram_gb=16,
        starts_at=datetime.now(timezone.utc),
        deadline=datetime.now(timezone.utc).replace(hour=23, minute=59),
        data_tier="PEER_REVIEWED",
    )

    async def main():
        ev = await evaluate_round(r, prof, current_gpu_vram_gb=24, current_load=0.3, my_tier="SILVER")
        print("평가 결과:")
        for k, v in ev.items():
            print(f"  {k}: {v}")
        print("참여?", should_accept(ev))

    asyncio.run(main())
