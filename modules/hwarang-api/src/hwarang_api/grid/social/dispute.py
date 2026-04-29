"""답변 충돌 해결 — LLM 심판.

여러 에이전트가 같은 질문에 다른 답변을 줬을 때 LLM 으로 한 명을 선택.
승자/패자 평판은 ``reputation.record_dispute`` 로 즉시 반영한다.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from hwarang_api.grid.social.reputation import record_dispute
from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


_JUDGE_SYSTEM = (
    "당신은 한국어 전문 심판입니다. 주어진 N 개 에이전트 답변 중 "
    "가장 정확하고 출처가 신뢰할 만한 답변 1 개를 고르세요. "
    "오직 다음 JSON 한 개만 출력하세요. 코드블록·해설 금지.\n"
    '{"winner_agent_id": "<agent_id>", '
    '"reason": "<한국어 1~2문장 사유>", '
    '"confidence": <0.0~1.0>}'
)


def _safe_parse(text: str) -> Optional[dict]:
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    s = cleaned.find("{")
    e = cleaned.rfind("}")
    if s == -1 or e == -1 or e <= s:
        return None
    try:
        obj = json.loads(cleaned[s : e + 1])
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _format_answers(answers: list[dict]) -> str:
    """answers: [{agent_id, content, sources?}]"""
    parts: list[str] = []
    for i, a in enumerate(answers, 1):
        aid = str(a.get("agent_id", f"agent_{i}"))
        content = str(a.get("content", "")).strip()
        sources = a.get("sources") or []
        src_text = ", ".join(str(s) for s in sources) if sources else "(출처 없음)"
        parts.append(
            f"[#{i}] agent_id={aid}\n"
            f"  답변: {content}\n"
            f"  출처: {src_text}"
        )
    return "\n\n".join(parts)


async def resolve_dispute(answers: list[dict], update_reputation: bool = True) -> dict:
    """N 개 답변 중 승자 선택.

    Parameters
    ----------
    answers : list[dict]
        ``[{"agent_id": str, "content": str, "sources": list[str]}]``.
    update_reputation : bool
        True 면 승자/패자 평판 즉시 업데이트.

    Returns
    -------
    dict
        ``{winner_agent_id, reason, confidence, fallback?}``. 입력이 비면
        ``{winner_agent_id: "", ...}``.
    """
    answers = [a for a in (answers or []) if isinstance(a, dict) and a.get("content")]
    if not answers:
        return {
            "winner_agent_id": "",
            "reason": "입력 답변 없음.",
            "confidence": 0.0,
            "fallback": True,
        }
    if len(answers) == 1:
        winner = str(answers[0].get("agent_id", ""))
        if update_reputation and winner:
            try:
                await record_dispute(winner, won=True)
            except Exception as exc:  # noqa: BLE001
                logger.warning("dispute: 단일 답변 평판 업데이트 실패: %s", exc)
        return {
            "winner_agent_id": winner,
            "reason": "후보 답변이 1 개뿐이므로 자동 채택.",
            "confidence": 1.0,
            "fallback": False,
        }

    valid_ids = {str(a.get("agent_id", "")) for a in answers if a.get("agent_id")}
    formatted = _format_answers(answers)
    prompt = (
        f"질문에 대한 {len(answers)}개의 답변 후보가 있습니다.\n\n"
        f"{formatted}\n\n"
        "위 답변 중 가장 정확하고 출처가 신뢰할 만한 것의 agent_id 를 골라 "
        "지정된 JSON 형식으로만 답하세요."
    )

    parsed: Optional[dict] = None
    try:
        resp = await llm_chat(prompt, system=_JUDGE_SYSTEM, max_tokens=300)
        parsed = _safe_parse(resp)
        if parsed is None:
            # 1 회 재시도
            resp = await llm_chat(prompt, system=_JUDGE_SYSTEM, max_tokens=300)
            parsed = _safe_parse(resp)
    except Exception as exc:  # noqa: BLE001
        logger.warning("dispute: LLM 호출 실패: %s", exc)
        parsed = None

    if parsed is None:
        # 폴백: 출처 수가 가장 많은 답변
        best = max(answers, key=lambda a: len(a.get("sources") or []))
        winner = str(best.get("agent_id", ""))
        result = {
            "winner_agent_id": winner,
            "reason": "LLM 심판 실패 — 출처 수 기준 폴백.",
            "confidence": 0.3,
            "fallback": True,
        }
    else:
        winner = str(parsed.get("winner_agent_id", "")).strip()
        if winner not in valid_ids:
            # LLM 이 잘못된 id 를 줬으면 첫 답변 폴백
            winner = str(answers[0].get("agent_id", ""))
        try:
            conf = float(parsed.get("confidence", 0.6))
        except (TypeError, ValueError):
            conf = 0.6
        result = {
            "winner_agent_id": winner,
            "reason": str(parsed.get("reason") or ""),
            "confidence": max(0.0, min(1.0, conf)),
            "fallback": False,
        }

    # 평판 업데이트 (best-effort)
    if update_reputation and result["winner_agent_id"]:
        try:
            await record_dispute(result["winner_agent_id"], won=True)
            for a in answers:
                aid = str(a.get("agent_id", ""))
                if aid and aid != result["winner_agent_id"]:
                    await record_dispute(aid, won=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("dispute: 평판 업데이트 실패: %s", exc)

    return result


__all__ = ["resolve_dispute"]
