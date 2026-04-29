"""코드 패턴 추출 — 블로그/SO 글에서 재사용 가능 패턴 분류.

매 6시간 cron 으로 호출. 최근 ingest 된 ``domain="code"`` 사실 중
코드 블록(``--- 코드 ---``) 또는 마크다운 펜스(```` ``` ````)가 포함된 것을
LLM 으로 분류해서 ``CodePattern`` 모델로 저장.

사용:
    from hwarang_api.research.code_pattern_extractor import (
        extract_patterns_from_recent_facts,
    )
    stats = await extract_patterns_from_recent_facts(window_hours=6)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone

from hwarang_api.db import prisma
from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


PATTERN_CLASSIFY_PROMPT = """다음 코드 + 설명에서 재사용 가능한 패턴을 추출해라.

코드:
{code}

설명:
{explanation}

JSON 출력 (JSON 만, 다른 텍스트 금지):
{{
  "pattern_name": "useDebounce, retryWithBackoff 같은 한국어/영문 이름",
  "category": "hook|utility|architecture|antipattern|optimization|design_pattern",
  "language": "javascript|python|rust|go|typescript|...",
  "framework": "react|fastapi|... (없으면 빈 문자열)",
  "summary": "5줄 한국어 요약",
  "use_case": "언제 사용하나 한 줄"
}}
JSON 만 출력:"""


VALID_CATEGORIES = {
    "hook",
    "utility",
    "architecture",
    "antipattern",
    "optimization",
    "design_pattern",
}


async def extract_patterns_from_recent_facts(
    window_hours: int = 6, max_facts: int = 100
) -> dict:
    """최근 N 시간 내 code 도메인 fact 들에서 패턴 추출.

    반환::

        {
          "facts_analyzed": int,
          "facts_with_code": int,
          "patterns_extracted": int,
          "errors": int,
          "elapsed_seconds": float,
        }
    """
    started = datetime.now(timezone.utc)
    cutoff = started - timedelta(hours=window_hours)

    try:
        facts = await prisma.knowledgefact.find_many(
            where={
                "domain": "code",
                "createdAt": {"gte": cutoff},
            },
            take=max_facts,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("KnowledgeFact 조회 실패: %s", exc)
        return {"facts_analyzed": 0, "patterns_extracted": 0, "error": str(exc)}

    if not facts:
        return {
            "facts_analyzed": 0,
            "facts_with_code": 0,
            "patterns_extracted": 0,
            "errors": 0,
            "elapsed_seconds": 0.0,
        }

    facts_with_code = 0
    extracted = 0
    errors = 0

    for f in facts:
        # 코드 블록 있는 경우만 (``` 펜스 또는 우리가 붙인 헤더)
        if "```" not in f.content and "--- 코드 ---" not in f.content:
            continue
        facts_with_code += 1

        try:
            patterns = await _classify(f.content)
            for p in patterns[:3]:  # 글당 최대 3 패턴
                if await _save_pattern(p, f):
                    extracted += 1
        except Exception as exc:  # noqa: BLE001
            errors += 1
            logger.debug("패턴 추출 실패 %s: %s", f.id, exc)

    return {
        "facts_analyzed": len(facts),
        "facts_with_code": facts_with_code,
        "patterns_extracted": extracted,
        "errors": errors,
        "elapsed_seconds": (
            datetime.now(timezone.utc) - started
        ).total_seconds(),
    }


_CODE_BLOCK_HEADER_RE = re.compile(r"--- 코드 ---\n(.*?)$", re.DOTALL)
_MD_FENCE_RE = re.compile(r"```(?:\w+\n)?(.*?)```", re.DOTALL)
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


async def _classify(content: str) -> list[dict]:
    """LLM 으로 패턴 분류 (단일 패턴만 추출 — 비용 절감)."""
    # 1) 코드 + 설명 분리: dev_source_crawler 의 헤더 우선, 없으면 ``` 펜스
    code = ""
    m = _CODE_BLOCK_HEADER_RE.search(content)
    if m:
        code = m.group(1).strip()
        explanation = content[: m.start()].strip()
    else:
        fences = _MD_FENCE_RE.findall(content)
        if fences:
            code = "\n\n".join(b.strip() for b in fences[:3])
            explanation = _MD_FENCE_RE.sub("", content).strip()
        else:
            return []

    if len(code) < 30:
        return []

    try:
        raw = await llm_chat(
            PATTERN_CLASSIFY_PROMPT.format(
                code=code[:2000],
                explanation=explanation[:1500],
            ),
            max_tokens=400,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("LLM 호출 실패: %s", exc)
        return []

    obj_match = _JSON_OBJECT_RE.search(raw or "")
    if not obj_match:
        return []
    try:
        parsed = json.loads(obj_match.group())
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, dict):
        return []
    return [parsed]


async def _save_pattern(pattern: dict, source_fact) -> bool:
    """CodePattern 으로 저장. 모델이 없으면 silently skip 하고 False."""
    name = (pattern.get("pattern_name") or "").strip()
    if not name:
        return False

    category = (pattern.get("category") or "utility").strip().lower()
    if category not in VALID_CATEGORIES:
        category = "utility"

    framework = (pattern.get("framework") or "").strip() or None

    data = {
        "patternName": name[:200],
        "category": category[:50],
        "language": (pattern.get("language") or "")[:50] or None,
        "framework": framework[:50] if framework else None,
        "summary": (pattern.get("summary") or "")[:1000],
        "useCase": (pattern.get("use_case") or "")[:300] or None,
        "sourceFactId": source_fact.id,
        "sourceUrl": getattr(source_fact, "sourceUrl", None),
    }
    try:
        await prisma.codepattern.create(data=data)
        return True
    except Exception as exc:  # noqa: BLE001
        # codepattern 모델이 prisma generate 안 됐거나 DB 없으면 skip
        logger.debug("CodePattern 저장 실패 (모델 미생성?): %s", exc)
        return False


__all__ = [
    "extract_patterns_from_recent_facts",
    "VALID_CATEGORIES",
]
