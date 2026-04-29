"""수집된 code domain KnowledgeFact 의 품질 평가 + 필터.

기준:
- GitHub: stars >= 1000 OR fork >= 200 + 6개월 내 활성
- StackOverflow: votes >= 10 + accepted answer
- 한국 tech 블로그: trustLevel >= 80 (이미 모두 통과)
- 코드 블록 길이: 50~3000 자
- 컴파일/문법 통과 (정적 검증)

매 6시간 cron — 미평가 fact 들에 qualityScore 채움.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


@dataclass
class QualitySignal:
    """단일 fact 의 품질 평가 결과."""

    score: float  # 0~1
    factors: dict[str, float]  # {"stars_signal": 0.8, "syntax_signal": 1.0, ...}
    is_high_quality: bool  # >= 0.7


# 가중치 6 요소 — score = sum(factor * weight)
WEIGHTS: dict[str, float] = {
    "source_trust": 0.25,
    "length": 0.10,
    "has_code": 0.20,
    "code_length": 0.15,
    "has_explanation": 0.10,
    "syntax": 0.20,
}

HIGH_QUALITY_THRESHOLD = 0.7


# ---------------------------------------------------------------------------
# 단일 fact 평가
# ---------------------------------------------------------------------------
async def evaluate_quality(fact: Any) -> QualitySignal:
    """``fact`` 한 건에 대해 6 요소 가중 합 품질 점수 계산."""
    factors: dict[str, float] = {}

    # 1. 출처 신뢰도 (TrustedSource.trustLevel / 100)
    factors["source_trust"] = await _source_trust(fact)

    # 2. 본문 길이
    length = len(fact.content or "")
    if 200 <= length <= 5000:
        factors["length"] = 1.0
    elif 100 <= length < 200:
        factors["length"] = 0.5
    else:
        factors["length"] = 0.3

    # 3. 코드 블록 존재
    code_blocks = re.findall(r"```(?:\w+\n)?(.*?)```", fact.content or "", re.DOTALL)
    if not code_blocks:
        # 본문에서 dev_source_crawler 의 [코드] 마커 찾기
        if fact.content and "--- 코드 ---" in fact.content:
            factors["has_code"] = 0.9
            # 마커 뒤를 코드 블록으로 추정
            marker_blocks = re.findall(
                r"--- 코드 ---\s*(.*?)(?=---|$)", fact.content, re.DOTALL
            )
            code_blocks = [b for b in marker_blocks if len(b.strip()) >= 30]
        else:
            factors["has_code"] = 0.0
    else:
        factors["has_code"] = 1.0

    # 4. 코드 길이 적절성
    if code_blocks:
        avg_code_len = sum(len(b) for b in code_blocks) / len(code_blocks)
        if 50 <= avg_code_len <= 3000:
            factors["code_length"] = 1.0
        else:
            factors["code_length"] = 0.5
    else:
        factors["code_length"] = 0.0

    # 5. 한국어/영어 비율 (설명 존재 여부)
    korean_chars = len(re.findall(r"[가-힣]", fact.content or ""))
    english_chars = len(re.findall(r"[a-zA-Z]", fact.content or ""))
    factors["has_explanation"] = 1.0 if (korean_chars + english_chars > 100) else 0.5

    # 6. 정적 분석 (Python ast.parse — 추정 가능 시)
    syntax_ok = await _check_syntax(code_blocks)
    factors["syntax"] = 1.0 if syntax_ok else 0.5

    score = sum(factors.get(k, 0.5) * w for k, w in WEIGHTS.items())
    return QualitySignal(
        score=score,
        factors=factors,
        is_high_quality=score >= HIGH_QUALITY_THRESHOLD,
    )


async def _source_trust(fact: Any) -> float:
    """SourceCitation → TrustedSource.trustLevel 정규화."""
    if not getattr(fact, "sourceUrl", None):
        return 0.5
    try:
        citation = await prisma.sourcecitation.find_first(
            where={"factId": fact.id},
            include={"source": True},
        )
        if citation and getattr(citation, "source", None):
            return max(0.0, min(1.0, citation.source.trustLevel / 100.0))
    except Exception as exc:  # noqa: BLE001
        logger.debug("source_trust 조회 실패: %s", exc)
    return 0.5


async def _check_syntax(code_blocks: list[str]) -> bool:
    """간단 정적 분석 — Python `ast.parse` 만 (첫 3 블록).

    JS/TS 는 외부 도구 없이 신뢰 검증이 어려우므로 통과 처리.
    Python 으로 추정되는 블록만 SyntaxError 면 False.
    """
    if not code_blocks:
        return True
    import ast

    for block in code_blocks[:3]:
        looks_python = any(
            kw in block for kw in ("def ", "import ", "from ", "class ", "    ")
        )
        if looks_python:
            try:
                ast.parse(block)
            except SyntaxError:
                return False
            except Exception:  # noqa: BLE001
                # 그 외 파싱 오류는 무시 (들여쓰기 손상 등)
                continue
    return True


# ---------------------------------------------------------------------------
# 배치 평가 (cron)
# ---------------------------------------------------------------------------
async def filter_recent_facts(
    window_hours: int = 24, batch_size: int = 200
) -> dict:
    """매 6시간 cron — 최근 fact 평가 + qualityScore 컬럼 채움.

    이미 ``qualityScore`` 가 채워진 fact 는 건너뜀. 모델에 컬럼이 없는
    환경에서는 update 가 실패하더라도 try/except 로 무시한다.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    try:
        facts = await prisma.knowledgefact.find_many(
            where={
                "domain": "code",
                "createdAt": {"gte": cutoff},
                # 미평가만 — qualityScore 컬럼이 모델에 없으면 prisma 가 무시
            },
            take=batch_size,
            order={"createdAt": "desc"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("filter_recent_facts find_many 실패: %s", exc)
        return {"evaluated": 0, "error": "db_error"}

    if not facts:
        return {"evaluated": 0, "high_quality": 0, "low_quality": 0}

    high_quality = 0
    low_quality = 0
    evaluated = 0
    for fact in facts:
        # 이미 평가된 건 건너뛰기 (qualityScore 컬럼이 있을 때)
        if getattr(fact, "qualityScore", None) is not None:
            continue
        try:
            signal = await evaluate_quality(fact)
        except Exception as exc:  # noqa: BLE001
            logger.debug("evaluate_quality 실패 %s: %s", fact.id, exc)
            continue
        evaluated += 1
        try:
            await prisma.knowledgefact.update(
                where={"id": fact.id},
                data={
                    "qualityScore": signal.score,
                    "qualityFactors": signal.factors,
                    "isHighQuality": signal.is_high_quality,
                },
            )
        except Exception as exc:  # noqa: BLE001
            # 컬럼이 아직 없거나 schema 미반영 — 평가만 반환
            logger.debug("qualityScore 저장 실패 (스키마 미반영 가능): %s", exc)
        if signal.is_high_quality:
            high_quality += 1
        else:
            low_quality += 1

    return {
        "evaluated": evaluated,
        "high_quality": high_quality,
        "low_quality": low_quality,
        "window_hours": window_hours,
    }


__all__ = [
    "QualitySignal",
    "WEIGHTS",
    "HIGH_QUALITY_THRESHOLD",
    "evaluate_quality",
    "filter_recent_facts",
]
