"""실시간 검색 API.

엔드포인트:
- ``POST /api/realtime/detect`` : 시간민감 질문 감지 (chat/route.ts 가 호출)
- ``POST /api/realtime/search`` : 통합 웹 검색 (Naver + Wikipedia)

내부 호출 전용 — ``HWARANG_INTERNAL_KEY`` 검사 (learning.py 패턴 재사용).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from hwarang_api.knowledge.realtime_search import realtime_search
from hwarang_api.knowledge.temporal_detector import detect_temporal
from hwarang_api.routers.learning import _check_internal_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/realtime", tags=["Realtime"])


def _require_internal_key(authorization: Optional[str] = Header(None)) -> bool:
    _check_internal_key(authorization)
    return True


class DetectRequest(BaseModel):
    message: str


class SearchRequest(BaseModel):
    queries: list[str] = Field(default_factory=list)
    top_k: int = 5


@router.post("/detect")
async def detect(req: DetectRequest, _: bool = Depends(_require_internal_key)):
    sig = detect_temporal(req.message)
    return {
        "needs_realtime": sig.needs_realtime,
        "confidence": sig.confidence,
        "signals": sig.signals,
        "suggested_queries": sig.suggested_queries,
    }


@router.post("/search")
async def search(req: SearchRequest, _: bool = Depends(_require_internal_key)):
    """주어진 쿼리들로 통합 검색.

    최대 3개 쿼리까지만 실행 (외부 API 쿼터 보호).
    """
    if not req.queries:
        return {"results": []}

    all_results = []
    for q in req.queries[:3]:
        try:
            hits = await realtime_search(q, top_k=req.top_k)
        except Exception as e:
            logger.warning(f"realtime_search '{q}' 실패: {e}")
            continue
        all_results.extend(hits)

    # 중복 제거
    seen: set[str] = set()
    unique = []
    for h in all_results:
        if not h.url or h.url in seen:
            continue
        seen.add(h.url)
        unique.append({
            "title": h.title,
            "url": h.url,
            "snippet": h.snippet,
            "source": h.source,
            "trust_score": h.trust_score,
        })

    # 신뢰도 정렬
    unique.sort(key=lambda x: -x["trust_score"])
    return {"results": unique[:10]}
