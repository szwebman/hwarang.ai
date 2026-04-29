"""Cognitive Orchestrator — 마스터의 결정을 에이전트들과 조율 (Phase 6).

흐름
----
1. 마스터가 ``cognitive_cycle`` 에서 "code 라운드 시작" 같은 결정.
2. ``consult_agents_for_round`` 가 적합 에이전트(VRAM/도메인 충족) 식별.
3. 각 에이전트한테 의향 질의 (HTTP ``/cognitive/consult``).
4. 응답 모아서 라운드 시작 여부 (≥ ``MIN_WILLING_AGENTS``) 최종 결정.
5. ``CognitiveMemory`` 에 토론(=의향조사) 이력 저장.

에이전트 모델 한계
------------------
``routers/grid.py`` 의 ``_agents`` 에는 ``domains`` / ``callback_url`` 이 현재
스키마상 항상 있지는 않다. 누락 시:
* 도메인 필터는 fallback (모든 에이전트 후보)
* callback_url 없는 에이전트는 ``"accept" + "callback 없음 — 기본 수락"`` 처리.
"""

from __future__ import annotations

import asyncio
import logging
import os

from hwarang_api.cognitive.memory import record_decision

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
MIN_WILLING_AGENTS = int(os.getenv("HWARANG_COGNITIVE_MIN_WILLING", "3"))
MAX_AGENTS_TO_CONSULT = int(os.getenv("HWARANG_COGNITIVE_MAX_CONSULT", "20"))
CONSULT_TIMEOUT_SEC = float(os.getenv("HWARANG_COGNITIVE_CONSULT_TIMEOUT", "5.0"))


# ---------------------------------------------------------------------------
# 메인 — 라운드 의향 조사
# ---------------------------------------------------------------------------
async def consult_agents_for_round(
    domain: str,
    estimated_minutes: int = 30,
    estimated_hwr: float = 100,
    min_vram_gb: float = 8,
) -> dict:
    """라운드 시작 전 에이전트들한테 의향 묻기.

    Returns:
        ``{
            agents_consulted, willing, willing_agents,
            declining, decline_reasons, should_proceed
        }``
    """
    try:
        from hwarang_api.routers.grid import _agents
    except Exception as exc:  # noqa: BLE001
        logger.warning("grid._agents import 실패: %s", exc)
        return {
            "agents_consulted": 0,
            "willing": 0,
            "should_proceed": False,
            "reason": "grid_unavailable",
        }

    # 적합 후보 — VRAM 충족, 도메인 일치 (도메인 미설정이면 통과)
    candidates: list[dict] = []
    for a in _agents.values():
        if a.get("vram_gb", 0) < min_vram_gb:
            continue
        agent_domains = a.get("domains")
        if agent_domains:
            if domain not in agent_domains and "general" not in agent_domains:
                continue
        # status 필터 — 가능하면 idle 또는 active 만
        status = a.get("status", "idle")
        if status in ("offline", "disabled"):
            continue
        candidates.append(a)

    if not candidates:
        await record_decision(
            actor="master",
            observed={"domain": domain, "candidates": 0},
            reasoning="적합 에이전트 없음",
            decision="abort",
            action_taken=f"consult_{domain}",
        )
        return {
            "agents_consulted": 0,
            "willing": 0,
            "should_proceed": False,
            "reason": "no_eligible_agents",
        }

    # 동시 의향 질의
    targets = candidates[:MAX_AGENTS_TO_CONSULT]
    consultations = await asyncio.gather(
        *[
            _ask_agent(a, domain, estimated_minutes, estimated_hwr, min_vram_gb)
            for a in targets
        ],
        return_exceptions=True,
    )

    willing: list[dict] = []
    declining: list[dict] = []
    for agent, response in zip(targets, consultations):
        if isinstance(response, Exception):
            logger.debug("agent %s 예외: %s", agent.get("agent_id"), response)
            continue
        action = (response or {}).get("action", "accept").lower()
        if action == "accept":
            willing.append(
                {
                    "agent_id": agent.get("agent_id"),
                    "confidence": float((response or {}).get("confidence", 0.7)),
                    "reasoning": (response or {}).get("reasoning", ""),
                }
            )
        else:
            declining.append(
                {
                    "agent_id": agent.get("agent_id"),
                    "reason": (response or {}).get("reasoning", ""),
                }
            )

    should_proceed = len(willing) >= MIN_WILLING_AGENTS

    # 결정 기록
    try:
        await record_decision(
            actor="master",
            observed={
                "domain": domain,
                "candidates": len(candidates),
                "consulted": len(targets),
                "willing": len(willing),
                "declining": len(declining),
                "min_willing": MIN_WILLING_AGENTS,
            },
            reasoning=(
                f"라운드 의향 조사 — {len(willing)}/{len(targets)} 동의, "
                f"임계 {MIN_WILLING_AGENTS}"
            ),
            decision="proceed" if should_proceed else "abort",
            action_taken=f"consult_{domain}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("consult 결정 기록 실패: %s", exc)

    return {
        "domain": domain,
        "agents_consulted": len(targets),
        "candidates_total": len(candidates),
        "willing": len(willing),
        "willing_agents": willing,
        "declining": len(declining),
        "decline_reasons": declining[:5],
        "min_willing_required": MIN_WILLING_AGENTS,
        "should_proceed": should_proceed,
    }


# ---------------------------------------------------------------------------
# 에이전트 1명 질의
# ---------------------------------------------------------------------------
async def _ask_agent(
    agent: dict,
    domain: str,
    estimated_minutes: int,
    estimated_hwr: float,
    min_vram_gb: float,
) -> dict:
    """에이전트한테 라운드 의향 묻기 (HTTP ``/cognitive/consult``).

    callback_url 누락 시 기본 수락 — 향후 register_agent 가 callback_url 을
    받게 되면 자동으로 진짜 질의가 발동.
    """
    agent_url = agent.get("callback_url") or agent.get("agent_url")
    if not agent_url:
        return {
            "action": "accept",
            "confidence": 0.6,
            "reasoning": "callback 없음 — 기본 수락",
        }

    try:
        import httpx
    except Exception:  # noqa: BLE001
        return {
            "action": "accept",
            "confidence": 0.5,
            "reasoning": "httpx 없음 — 기본 수락",
        }

    headers = {}
    callback_token = agent.get("callback_token")
    if callback_token:
        headers["Authorization"] = f"Bearer {callback_token}"

    try:
        async with httpx.AsyncClient(timeout=CONSULT_TIMEOUT_SEC) as client:
            resp = await client.post(
                f"{str(agent_url).rstrip('/')}/cognitive/consult",
                json={
                    "round_id": agent.get("_round_id", "consult"),
                    "domain": domain,
                    "estimated_minutes": estimated_minutes,
                    "estimated_hwr": estimated_hwr,
                    "min_vram_gb": min_vram_gb,
                    "sample_count": agent.get("_sample_count", 1000),
                },
                headers=headers,
            )
        if resp.status_code == 200:
            data = resp.json() if resp.content else {}
            if isinstance(data, dict):
                return data
        else:
            logger.debug(
                "agent %s consult HTTP %s: %s",
                agent.get("agent_id"), resp.status_code, resp.text[:200],
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("agent %s consult 실패: %s", agent.get("agent_id"), exc)

    # 응답 없음 = 기본 수락 (보수적이지 않게 — 라운드 시작을 막지 않도록)
    return {
        "action": "accept",
        "confidence": 0.5,
        "reasoning": "응답 없음 — 기본 수락",
    }


__all__ = [
    "MIN_WILLING_AGENTS",
    "MAX_AGENTS_TO_CONSULT",
    "consult_agents_for_round",
]
