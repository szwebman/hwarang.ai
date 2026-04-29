"""KnowledgeFact 의 코드 + 설명 → Q&A 페어 자동 생성.

학습 형식::

    {
      "instruction": "다음 기능을 React Hook 으로 구현해줘 — debounce 입력값",
      "response": "```typescript\\nimport { useState, useEffect } from 'react';\\n...```",
      "domain": "code",
      "language": "typescript",
      "framework": "react",
      "category": "hook"
    }

매 12시간 cron — high_quality fact 들 → CodePair 테이블.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from hwarang_api.db import prisma
from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


PAIR_BUILD_PROMPT = """다음 코드 + 설명에서 학습 데이터로 쓸 Q&A 페어 1~3개 생성해라.

코드:
{code}

설명:
{explanation}

JSON 배열만 출력 (각 페어마다 아래 키 모두 포함):
[
  {{
    "instruction": "사용자가 '~ 짜줘' 처럼 자연스럽게 한국어로 묻는 질문",
    "response": "코드 + 짧은 설명 (~ 100줄 이내, 마크다운 fence 포함)",
    "language": "javascript|typescript|python|...",
    "framework": "react|vue|fastapi|... (없으면 빈 문자열)",
    "category": "hook|utility|api|component|algorithm|test"
  }}
]

JSON 배열만 출력:"""

VALID_CATEGORIES = {"hook", "utility", "api", "component", "algorithm", "test"}


# ---------------------------------------------------------------------------
# 배치 생성 (cron)
# ---------------------------------------------------------------------------
async def build_pairs_from_high_quality(limit: int = 50) -> dict:
    """high_quality 인 code fact → CodePair 생성.

    이미 페어가 있는 fact 는 건너뜀. fact 당 최대 3 페어.
    """
    try:
        facts = await prisma.knowledgefact.find_many(
            where={
                "domain": "code",
                "isHighQuality": True,
            },
            take=limit,
            order={"createdAt": "desc"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("build_pairs find_many 실패: %s", exc)
        return {"pairs_created": 0, "error": "db_error"}

    if not facts:
        return {"facts_processed": 0, "pairs_created": 0}

    created = 0
    skipped = 0
    for fact in facts:
        # 이미 이 fact 로 만든 페어가 있으면 skip
        try:
            existing = await prisma.codepair.find_first(
                where={"sourceFactId": fact.id}
            )
        except Exception:  # noqa: BLE001
            existing = None
        if existing:
            skipped += 1
            continue

        try:
            pairs = await _generate_pairs(fact)
        except Exception as exc:  # noqa: BLE001
            logger.debug("페어 생성 실패 %s: %s", fact.id, exc)
            continue

        for p in pairs[:3]:
            instruction = (p.get("instruction") or "").strip()[:1000]
            response = (p.get("response") or "").strip()[:5000]
            if not instruction or not response:
                continue
            category = (p.get("category") or "").strip().lower()
            if category and category not in VALID_CATEGORIES:
                category = ""
            try:
                await prisma.codepair.create(
                    data={
                        "instruction": instruction,
                        "response": response,
                        "language": (p.get("language") or "").strip().lower()[:30],
                        "framework": (p.get("framework") or "").strip().lower()[:30],
                        "category": category[:30],
                        "sourceFactId": fact.id,
                        "executionStatus": "untested",
                        "qualityScore": getattr(fact, "qualityScore", None),
                    },
                )
                created += 1
            except Exception as exc:  # noqa: BLE001
                logger.debug("CodePair create 실패: %s", exc)

    return {
        "facts_processed": len(facts),
        "facts_skipped": skipped,
        "pairs_created": created,
    }


# ---------------------------------------------------------------------------
# LLM 호출 + 파싱
# ---------------------------------------------------------------------------
async def _generate_pairs(fact: Any) -> list[dict]:
    """LLM 으로 자연어 질문 + 정답 코드 페어 생성. 실패 시 빈 리스트."""
    code, explanation = _split_code_and_explanation(fact.content or "")
    if len(code) < 30:
        return []

    try:
        raw = await llm_chat(
            PAIR_BUILD_PROMPT.format(
                code=code[:3000],
                explanation=explanation[:1500],
            ),
            max_tokens=1500,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("llm_chat 실패: %s", exc)
        return []

    if not raw:
        return []

    # JSON 배열 찾기
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return []
    try:
        parsed = json.loads(m.group())
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [p for p in parsed if isinstance(p, dict)]


def _split_code_and_explanation(content: str) -> tuple[str, str]:
    """fact.content 에서 코드 블록과 자연어 설명 분리."""
    # 1) 마크다운 fence 우선
    fence = re.search(r"```(?:\w+\n)?(.*?)```", content, re.DOTALL)
    if fence:
        code = fence.group(1)
        explanation = (
            content[: fence.start()] + content[fence.end():]
        )
        return code.strip(), explanation.strip()

    # 2) dev_source_crawler 마커
    marker = re.search(r"--- 코드 ---\s*(.*)", content, re.DOTALL)
    if marker:
        code = marker.group(1).strip()
        explanation = content[: marker.start()].strip()
        return code, explanation

    return "", content.strip()


__all__ = [
    "VALID_CATEGORIES",
    "PAIR_BUILD_PROMPT",
    "build_pairs_from_high_quality",
]
