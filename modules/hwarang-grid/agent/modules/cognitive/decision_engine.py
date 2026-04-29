"""에이전트 자율 결정 — 라운드 제안 받았을 때 참여 여부.

작은 LLM (7B 이하, 권장 0.5B~1.5B) 또는 규칙 기반 fallback.
LLM 미설치/접속 실패 시 자동으로 규칙 기반.

호출:
    decision = await decide_about_round(offer, use_llm=False)
    if decision.action == "accept":
        ...
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

try:
    import httpx  # type: ignore
except Exception:  # pragma: no cover
    httpx = None  # type: ignore

from .state_collector import AgentState

logger = logging.getLogger(__name__)


@dataclass
class RoundOffer:
    round_id: str
    domain: str
    estimated_minutes: int
    estimated_hwr: float
    min_vram_gb: float
    sample_count: int


@dataclass
class Decision:
    action: str  # "accept" | "decline" | "negotiate"
    confidence: float  # 0~1
    reasoning: str
    suggested_alternatives: list[str] = field(default_factory=list)


# ─── 규칙 기반 (LLM 없을 때 폴백) ─────────────


def rule_based_decide(state: AgentState, offer: RoundOffer) -> Decision:
    """간단 규칙 — LLM 없을 때 폴백.

    7가지 결정 규칙(우선순위 순):
        1) GPU VRAM 부족 → decline
        2) 사용자 활동 + 배터리 → decline (방해/전력)
        3) 야간 + 도메인 일치 → accept (최적 슬롯)
        4) 오늘 라운드 ≥10 → decline (피로)
        5) 최근 품질 <0.5 → decline (양보)
        6) 도메인 전문성 보유 → accept (적극)
        7) 기본 → accept
    """

    reasons: list[str] = []

    # 1) GPU 충분?
    available_vram = state.gpu_vram_total_gb - state.gpu_vram_used_gb
    if state.gpu_vram_total_gb > 0 and available_vram < offer.min_vram_gb:
        return Decision(
            action="decline",
            confidence=0.95,
            reasoning=f"GPU VRAM 부족 ({available_vram:.1f}GB / 필요 {offer.min_vram_gb}GB)",
        )

    # 2) 사용자 활동 중 + 배터리?
    if state.is_user_active and state.is_on_battery:
        return Decision(
            action="decline",
            confidence=0.85,
            reasoning="사용자 활동 중 + 배터리 사용 — 방해될 수 있음",
        )

    # 도메인 전문성
    has_expertise = (
        offer.domain in state.available_loras
        or any(c for c in state.expert_credentials if offer.domain in c.lower())
    )
    if has_expertise:
        reasons.append(f"{offer.domain} 도메인 전문")

    # 3) 야간 + 도메인 일치 → 적극 참여
    if state.is_night and (has_expertise or offer.domain == "general"):
        reasons.append("야간 + 도메인 일치 — 최적")
        return Decision(
            action="accept",
            confidence=0.9,
            reasoning=", ".join(reasons),
        )

    # 4) 오늘 이미 너무 많이 함?
    if state.rounds_completed_today >= 10:
        return Decision(
            action="decline",
            confidence=0.7,
            reasoning=f"오늘 라운드 {state.rounds_completed_today}회 완료 — 충분",
        )

    # 5) 최근 품질 점수 낮음 → 주저
    if state.last_round_score is not None and state.last_round_score < 0.5:
        return Decision(
            action="decline",
            confidence=0.6,
            reasoning="최근 품질 낮음 — 다른 에이전트 양보",
        )

    # 6) 도메인 전문성 보유 → 적극
    if has_expertise:
        return Decision(
            action="accept",
            confidence=0.85,
            reasoning="조건 적합 + " + ", ".join(reasons),
        )

    # 7) 기본 — 수락
    return Decision(
        action="accept",
        confidence=0.7,
        reasoning="조건 적합" + (" + " + ", ".join(reasons) if reasons else ""),
    )


# ─── LLM 기반 (선택) ────────────────────────

DECIDE_PROMPT = """당신은 화랑 그리드 에이전트의 인지 엔진입니다. 다음 라운드 제안을 받았습니다.

## 라운드 제안
- 도메인: {domain}
- 예상 시간: {minutes}분
- 예상 보상: {hwr} HWR
- 필요 VRAM: {min_vram}GB
- 샘플: {samples}개

## 내 현재 상태
{state}

JSON 답변:
{{
  "action": "accept|decline|negotiate",
  "confidence": 0.0~1.0,
  "reasoning": "왜 이렇게 결정했는지 (한국어 한 줄)",
  "suggested_alternatives": []
}}

JSON 만 출력:"""


async def llm_decide(
    state: AgentState,
    offer: RoundOffer,
    llm_url: str = "http://localhost:8003",
) -> Decision:
    """LLM 으로 결정 — llm_url 가 있을 때만.

    작은 모델 (Qwen 0.5B 등) 을 에이전트 PC 에 띄워서 사용.
    없으면 rule_based_decide 폴백.
    """
    if httpx is None:
        logger.debug("httpx 미설치 — 규칙 기반 폴백")
        return rule_based_decide(state, offer)

    state_dict = state.__dict__
    state_text = "\n".join(f"- {k}: {v}" for k, v in state_dict.items())

    prompt = DECIDE_PROMPT.format(
        domain=offer.domain,
        minutes=offer.estimated_minutes,
        hwr=offer.estimated_hwr,
        min_vram=offer.min_vram_gb,
        samples=offer.sample_count,
        state=state_text,
    )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{llm_url}/v1/chat/completions",
                json={
                    "model": "decision-llm",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                    "temperature": 0.3,
                },
            )
        if resp.status_code != 200:
            logger.debug("LLM 응답 %s — 규칙 폴백", resp.status_code)
            return rule_based_decide(state, offer)

        data = resp.json()
        raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            parsed = json.loads(m.group())
            action = str(parsed.get("action", "accept"))[:20]
            if action not in ("accept", "decline", "negotiate"):
                action = "accept"
            alts = parsed.get("suggested_alternatives") or []
            if not isinstance(alts, list):
                alts = []
            return Decision(
                action=action,
                confidence=float(parsed.get("confidence", 0.7)),
                reasoning=str(parsed.get("reasoning", ""))[:300],
                suggested_alternatives=[str(a) for a in alts[:5]],
            )
    except Exception as e:
        logger.debug(f"LLM 결정 실패, 규칙 폴백: {e}")

    return rule_based_decide(state, offer)


# ─── 메인 진입점 ─────────────────────────────


async def decide_about_round(
    offer: RoundOffer,
    use_llm: bool = False,
    llm_url: Optional[str] = None,
) -> Decision:
    """라운드 제안 → 결정.

    Args:
        offer: 마스터에서 받은 라운드 메타.
        use_llm: LLM 모델 띄워뒀으면 True. 기본은 rule-based.
        llm_url: LLM 엔드포인트(/v1/chat/completions). None 이면 환경변수
            HWARANG_AGENT_DECISION_LLM_URL 또는 기본값 사용.
    """
    from .state_collector import collect_state
    state = await collect_state()

    if use_llm:
        import os
        url = (
            llm_url
            or os.environ.get("HWARANG_AGENT_DECISION_LLM_URL")
            or "http://localhost:8003"
        )
        return await llm_decide(state, offer, llm_url=url)
    return rule_based_decide(state, offer)
