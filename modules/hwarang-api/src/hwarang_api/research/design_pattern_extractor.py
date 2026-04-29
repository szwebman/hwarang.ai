"""디자인 패턴 추출 — 글에서 시각 패턴 / 트렌드 분류.

매 12시간 cron — 최근 ``domain="design"`` 도메인 fact 들을 LLM 으로 분류해서
``DesignPattern`` 모델로 저장.

분류 차원:
  - trend_keywords  : minimalism / brutalism / glassmorphism …
  - layout_category : hero / grid / split / asymmetric / magazine / fullscreen
  - color_mood      : warm / cool / monochrome / vibrant / muted
  - typography      : serif / sans / display / monospace / mixed
  - applicable_to   : landing / dashboard / mobile_app / marketing …

사용:
    from hwarang_api.research.design_pattern_extractor import (
        extract_design_patterns,
    )
    stats = await extract_design_patterns(window_hours=24)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone

from hwarang_api.db import prisma
from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


# 알려진 디자인 트렌드 어휘 (LLM 답변 후처리 검증용)
DESIGN_TRENDS: list[str] = [
    "minimalism",
    "brutalism",
    "neumorphism",
    "glassmorphism",
    "skeuomorphism",
    "flat design",
    "material you",
    "dark mode",
    "light mode",
    "gradient",
    "noise texture",
    "kinetic typography",
    "3d",
    "isometric",
    "claymorphism",
    "swiss design",
    "memphis design",
    "vaporwave",
]


VALID_LAYOUTS = {
    "hero",
    "grid",
    "split",
    "asymmetric",
    "magazine",
    "fullscreen",
    "unknown",
}


PATTERN_CLASSIFY_PROMPT = """다음 디자인 글/사이트 정보에서 시각 패턴을 분류해라.

내용:
{content}

이미지 URL: {images}
태그: {tags}

JSON 출력 (JSON 만, 다른 텍스트 금지):
{{
  "trend_keywords": ["minimalism", ...],
  "layout_category": "hero|grid|split|asymmetric|magazine|fullscreen",
  "color_mood": "warm|cool|monochrome|vibrant|muted",
  "typography_style": "serif|sans|display|monospace|mixed",
  "summary": "이 디자인 패턴 한국어 5줄",
  "applicable_to": ["landing", "dashboard", "mobile_app", "marketing", ...]
}}
JSON 만 출력:"""


_IMAGES_LINE_RE = re.compile(r"이미지: (.*?)(?:\n|$)")
_TAGS_LINE_RE = re.compile(r"태그: (.*?)(?:\n|$)")
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


async def extract_design_patterns(
    window_hours: int = 24, max_facts: int = 50
) -> dict:
    """매 12시간 cron — design 도메인 사실에서 패턴 추출.

    반환::

        {
          "facts_analyzed": int,
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
                "domain": "design",
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
            "patterns_extracted": 0,
            "errors": 0,
            "elapsed_seconds": 0.0,
        }

    extracted = 0
    errors = 0
    for f in facts:
        try:
            pattern = await _classify(f)
            if pattern and await _save_pattern(pattern, f):
                extracted += 1
        except Exception as exc:  # noqa: BLE001
            errors += 1
            logger.debug("design pattern 추출 실패 %s: %s", f.id, exc)

    return {
        "facts_analyzed": len(facts),
        "patterns_extracted": extracted,
        "errors": errors,
        "elapsed_seconds": (
            datetime.now(timezone.utc) - started
        ).total_seconds(),
    }


async def _classify(fact) -> dict | None:
    """LLM 에 디자인 패턴 분류 요청 → JSON dict."""
    content = fact.content or ""
    images_match = _IMAGES_LINE_RE.search(content)
    tags_match = _TAGS_LINE_RE.search(content)

    try:
        raw = await llm_chat(
            PATTERN_CLASSIFY_PROMPT.format(
                content=content[:2500],
                images=images_match.group(1) if images_match else "(없음)",
                tags=tags_match.group(1) if tags_match else "(없음)",
            ),
            max_tokens=400,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("design LLM 호출 실패: %s", exc)
        return None

    obj_match = _JSON_OBJECT_RE.search(raw or "")
    if not obj_match:
        return None
    try:
        parsed = json.loads(obj_match.group())
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


async def _save_pattern(pattern: dict, source_fact) -> bool:
    """``DesignPattern`` 으로 저장. 모델이 없으면 silently skip 후 False."""
    layout = (pattern.get("layout_category") or "unknown").strip().lower()
    if layout not in VALID_LAYOUTS:
        layout = "unknown"

    trend_keywords = pattern.get("trend_keywords") or []
    if not isinstance(trend_keywords, list):
        trend_keywords = []
    applicable_to = pattern.get("applicable_to") or []
    if not isinstance(applicable_to, list):
        applicable_to = []

    data = {
        "trendKeywords": [str(t)[:50] for t in trend_keywords[:10]],
        "layoutCategory": layout[:50],
        "colorMood": (pattern.get("color_mood") or "")[:30] or None,
        "typographyStyle": (pattern.get("typography_style") or "")[:30] or None,
        "summary": (pattern.get("summary") or "")[:1500],
        "applicableTo": [str(a)[:50] for a in applicable_to[:10]],
        "sourceFactId": getattr(source_fact, "id", None),
        "sourceUrl": getattr(source_fact, "sourceUrl", None),
    }
    try:
        await prisma.designpattern.create(data=data)
        return True
    except Exception as exc:  # noqa: BLE001
        # designpattern 모델이 prisma generate 안 됐거나 DB 없으면 skip
        logger.debug("DesignPattern 저장 실패 (모델 미생성?): %s", exc)
        return False


__all__ = [
    "extract_design_patterns",
    "DESIGN_TRENDS",
    "VALID_LAYOUTS",
]
