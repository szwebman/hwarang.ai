"""통합 신뢰 (Unified Trust) 라우터.

엔드포인트
----------
* ``GET /api/trust/{kind}/{entity_id}``  — 단일 entity 점수 + breakdown
* ``GET /api/trust/{kind}/top/{n}``      — 상위 N 리더보드

``kind`` 는 ``agent`` 또는 ``source``. 실제 저장은 각 도메인 모듈이 담당하고,
이 라우터는 ``UnifiedTrust`` facade 를 통해 동일한 모양의 응답으로 정규화한다.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from hwarang_api.cognitive.trust import TrustKind, UnifiedTrust
from hwarang_api.cognitive.trust.unified_trust import TrustNotAvailable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trust", tags=["Trust"])


def _parse_kind(kind: str) -> TrustKind:
    try:
        return TrustKind(kind)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"unknown trust kind: {kind!r} (use 'agent' or 'source')",
        ) from exc


@router.get("/{kind}/top/{n}")
async def trust_top(kind: str, n: int = 10) -> dict:
    """상위 N 리더보드. ``n`` 은 [1, 100] 으로 클램프."""
    tk = _parse_kind(kind)
    try:
        rows = await UnifiedTrust.top_n(tk, n=n)
    except TrustNotAvailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"kind": tk.value, "count": len(rows), "items": rows}


@router.get("/{kind}/{entity_id}")
async def trust_single(kind: str, entity_id: str) -> dict:
    """단일 entity 의 신뢰 점수 + 도메인별 세부 메타."""
    tk = _parse_kind(kind)
    try:
        return await UnifiedTrust.get_breakdown(tk, entity_id)
    except TrustNotAvailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


__all__ = ["router"]
