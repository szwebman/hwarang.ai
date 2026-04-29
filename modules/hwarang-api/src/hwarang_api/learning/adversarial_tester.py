"""Self-Adversarial — 화랑이 자기 답변을 공격해서 약점 발견 (HSEE Phase 5).

매일 sleep cycle (04:00 KST) 직후 호출:

1. 어제 신뢰도 높은 답변 N개 sampling (rating=1, isSatisfied=True)
2. 적대적 LLM 이 그 답변을 깨려고 시도 (반박 / 재질문 / 함정 3가지)
3. 화랑이 같은 질문 재공격에 다시 답할 때 결론이 같은지 검증
4. 결론이 바뀌면 → 약점 발견 → ReplaySample 에 priority 10.0 으로 등록

핵심 효과:
- 학습 큐에 자동 어려운 케이스 보강
- catastrophic forgetting 사후 탐지
- 사용자 직접 신호 없이도 자기개선 사이클 추가
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from hwarang_api.db import prisma
from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────
# 프롬프트
# ────────────────────────────────────────────────────────────
ATTACK_PROMPT = """다음 화랑 AI 의 답변을 공격하는 질문 3개를 생성해라.
공격 방식:
1. 반박 — 답변과 반대되는 사실 / 예외 사례 제시
2. 재질문 — 같은 주제 다른 각도
3. 함정 — 답변이 빠뜨린 디테일 노리기

원래 질문: {question}
화랑 답변: {response}

형식: JSON ["공격 질문1", "공격 질문2", "공격 질문3"]
JSON 만 출력:"""


CONTRADICTION_PROMPT = """원래 답변과 새 답변이 사실관계에서 모순되는지 판단해라.

원래 답변: {original}
새 답변: {new}

JSON: {{"contradicts": true|false, "reason": "이유 한 줄"}}
JSON 만 출력:"""


ADVERSARIAL_PRIORITY = 10.0  # 일반 1.0 의 10배 — 학습 시 반드시 포함되도록
ADVERSARIAL_DIFFICULTY = 1.0  # 어려운 케이스로 표시


# ────────────────────────────────────────────────────────────
# 메인 진입점
# ────────────────────────────────────────────────────────────
async def run_adversarial_self_play(samples: int = 20) -> dict:
    """매일 sleep cycle 다음 단계에서 호출. 약점 발견 + replay buffer 등록.

    Parameters
    ----------
    samples : int
        공격 대상 샘플 수 (기본 20). 후보 풀은 ``samples * 5`` 만큼 조회한다.

    Returns
    -------
    dict
        ``{"attacked", "weaknesses_found", "weakness_rate"}``.
    """
    yesterday = datetime.now(timezone.utc) - timedelta(hours=24)

    try:
        feedback = await prisma.rlhffeedback.find_many(
            where={
                "createdAt": {"gte": yesterday},
                "isSatisfied": True,
                "rating": 1,
            },
            take=samples * 5,
            order={"createdAt": "desc"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"adversarial: RLHFFeedback 조회 실패: {exc}")
        return {"attacked": 0, "weaknesses_found": 0, "error": str(exc)}

    if not feedback:
        return {"attacked": 0, "weaknesses_found": 0}

    weaknesses = 0
    attacked = 0

    for fb in feedback[:samples]:
        try:
            if not getattr(fb, "conversationId", None):
                continue

            messages = await prisma.message.find_many(
                where={"conversationId": fb.conversationId},
                order={"createdAt": "asc"},
                take=10,
            )
            if len(messages) < 2:
                continue

            user_msg = next((m for m in messages if m.role == "user"), None)
            asst_msg = next((m for m in messages if m.role == "assistant"), None)
            if not user_msg or not asst_msg:
                continue

            attacked += 1

            # 1. 공격 질문 생성
            raw = await llm_chat(
                ATTACK_PROMPT.format(
                    question=user_msg.content[:500],
                    response=asst_msg.content[:1000],
                )
            )
            attacks = _parse_list(raw)
            if not attacks:
                continue

            # 2. 각 공격에 화랑 재질의
            broke = False
            broke_reason = ""
            for attack in attacks[:3]:
                new_response = await _re_query_hwarang(
                    attack, getattr(fb, "domain", None)
                )
                if not new_response:
                    continue

                contra = await _check_contradiction(asst_msg.content, new_response)
                if contra.get("contradicts"):
                    broke = True
                    broke_reason = contra.get("reason", "")[:200]
                    break  # 한 공격이라도 깨면 약점 — 추가 공격 생략

            if broke:
                # 3. ReplaySample 에 priority 높게 등록 (어려운 케이스)
                try:
                    await prisma.replaysample.create(
                        data={
                            "domain": getattr(fb, "domain", None) or "general",
                            "prompt": user_msg.content[:2000],
                            "expectedOutput": asst_msg.content[:2000],
                            "priority": ADVERSARIAL_PRIORITY,
                            "difficulty": ADVERSARIAL_DIFFICULTY,
                            "rlhfRating": 1,
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"adversarial: replaysample.create 실패: {exc}")

                weaknesses += 1

                # 4. RLHFFeedback 에 흔적 (followupMsg 에 표시)
                try:
                    await prisma.rlhffeedback.update(
                        where={"id": fb.id},
                        data={
                            "isSatisfied": False,
                            "followupMsg": f"[adversarial] {broke_reason}",
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug(f"adversarial: rlhffeedback.update 실패: {exc}")

        except Exception as exc:  # noqa: BLE001
            logger.debug(f"adversarial sample 실패: {exc}")
            continue

    rate = weaknesses / attacked if attacked else 0
    logger.info(
        "adversarial: attacked=%d weaknesses=%d rate=%.2f",
        attacked,
        weaknesses,
        rate,
    )
    return {
        "attacked": attacked,
        "weaknesses_found": weaknesses,
        "weakness_rate": rate,
    }


# ────────────────────────────────────────────────────────────
# 조회 — 관리자 대시보드용
# ────────────────────────────────────────────────────────────
async def list_adversarial_findings(days: int = 7, limit: int = 100) -> dict:
    """발견된 약점 목록 — RLHFFeedback.followupMsg 가 ``[adversarial]`` 으로 시작."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        rows = await prisma.rlhffeedback.find_many(
            where={
                "createdAt": {"gte": cutoff},
                "followupMsg": {"startsWith": "[adversarial]"},
            },
            order={"createdAt": "desc"},
            take=limit,
        )
    except Exception as exc:  # noqa: BLE001
        return {"count": 0, "items": [], "error": str(exc)}

    items = []
    for r in rows:
        items.append(
            {
                "id": r.id,
                "domain": getattr(r, "domain", None),
                "model": getattr(r, "modelName", None),
                "reason": (getattr(r, "followupMsg", "") or "").replace(
                    "[adversarial] ", ""
                )[:200],
                "created_at": r.createdAt.isoformat()
                if getattr(r, "createdAt", None)
                else None,
            }
        )
    return {"count": len(items), "days": days, "items": items}


# ────────────────────────────────────────────────────────────
# 내부 헬퍼
# ────────────────────────────────────────────────────────────
async def _re_query_hwarang(question: str, domain: Optional[str] = None) -> str:
    """화랑 chat API 재호출 (내부 회로).

    Next.js 의 ``/api/chat`` 을 internal key 로 호출. verify=False (속도 우선).
    """
    api_url = os.getenv("HWARANG_INTERNAL_URL", "http://localhost:3000")
    internal_key = os.getenv("HWARANG_INTERNAL_KEY", "")

    try:
        import httpx
    except Exception:  # pragma: no cover
        return ""

    headers = {"Content-Type": "application/json"}
    if internal_key:
        headers["Authorization"] = f"Bearer {internal_key}"

    payload: dict[str, Any] = {
        "messages": [{"role": "user", "content": question}],
        "stream": False,
        "verify": False,  # adversarial 은 verify 안 함 (속도)
        "federated": False,  # 단일 모델 답으로 충분
    }
    if domain:
        payload["domain_hint"] = domain

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{api_url.rstrip('/')}/api/chat",
                headers=headers,
                json=payload,
            )
        if resp.status_code != 200:
            return ""
        data = resp.json()
        return (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            or ""
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"adversarial _re_query 실패: {exc}")
        return ""


async def _check_contradiction(original: str, new: str) -> dict:
    """LLM 으로 모순 판단."""
    try:
        raw = await llm_chat(
            CONTRADICTION_PROMPT.format(
                original=original[:1500],
                new=new[:1500],
            )
        )
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception:  # noqa: BLE001
        pass
    return {"contradicts": False}


def _parse_list(raw: str) -> list[str]:
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return []
    try:
        parsed = json.loads(m.group())
        return [str(x) for x in parsed if x]
    except Exception:  # noqa: BLE001
        return []


__all__ = [
    "run_adversarial_self_play",
    "list_adversarial_findings",
    "ADVERSARIAL_PRIORITY",
]
