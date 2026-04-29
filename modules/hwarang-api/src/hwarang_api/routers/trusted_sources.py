"""Trusted Source Network REST API.

화이트리스트 출처 CRUD + 즉시 크롤 트리거 + 통계 + cross-verify 엔드포인트.

엔드포인트:
  GET    /api/sources               목록 조회 (domain, type, minTrust, isWhitelisted)
  POST   /api/sources               신규 등록 (관리자)
  PUT    /api/sources/{id}          수정 (trustLevel 등)
  DELETE /api/sources/{id}          삭제
  POST   /api/sources/{id}/crawl    즉시 크롤 트리거 (테스트/관리자)
  GET    /api/sources/{id}/stats    출처 통계
  POST   /api/verify                {claim, domain} → ClaimVerification

인증:
  - 변경/크롤 트리거 작업은 ``require_admin`` 가드 (admin- 프리픽스 키)
  - 조회/verify 는 일반 ``require_user``
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from hwarang_api.knowledge.cross_verifier import verify_claim
from hwarang_api.knowledge.source_crawler import crawl_one_source

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# 인증 (knowledge.py 와 동일한 단순 헤더 가드)
# ---------------------------------------------------------------------------
async def require_admin(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    if not x_api_key or not x_api_key.startswith("admin-"):
        raise HTTPException(status_code=401, detail="admin API key required")
    return x_api_key


async def require_user(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    return x_api_key


async def _get_prisma():
    try:
        from hwarang_api.db import prisma  # type: ignore

        if hasattr(prisma, "is_connected") and not prisma.is_connected():
            await prisma.connect()  # type: ignore[attr-defined]
        return prisma
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="prisma not installed") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"DB unavailable: {exc}") from exc


# ---------------------------------------------------------------------------
# Pydantic
# ---------------------------------------------------------------------------
class SourceCreate(BaseModel):
    domain: str
    displayName: str
    type: str = Field(
        ..., description="government | academic | news_major | news_minor | "
        "fact_checker | medical | financial"
    )
    trustLevel: int = Field(..., ge=0, le=100)
    isWhitelisted: bool = True
    isPrimarySource: bool = False
    isActive: bool = True
    domains: list[str] = []
    crawlSchedule: str = "0 */6 * * *"
    crawlMethod: str = "rss"
    rssUrl: str | None = None
    apiEndpoint: str | None = None
    apiKey: str | None = None
    selectorJson: dict | None = None
    notes: str | None = None


class SourceUpdate(BaseModel):
    displayName: str | None = None
    type: str | None = None
    trustLevel: int | None = Field(None, ge=0, le=100)
    isWhitelisted: bool | None = None
    isPrimarySource: bool | None = None
    isActive: bool | None = None
    domains: list[str] | None = None
    crawlSchedule: str | None = None
    crawlMethod: str | None = None
    rssUrl: str | None = None
    apiEndpoint: str | None = None
    apiKey: str | None = None
    selectorJson: dict | None = None
    notes: str | None = None


class VerifyRequest(BaseModel):
    claim: str = Field(..., min_length=2, max_length=2000)
    domain: str = "general"
    top_k: int = Field(20, ge=1, le=100)


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _row_to_dict(row: Any) -> dict:
    """Prisma row → JSON-safe dict."""
    if hasattr(row, "model_dump"):
        d = row.model_dump()
    elif isinstance(row, dict):
        d = dict(row)
    else:
        d = {k: getattr(row, k) for k in dir(row) if not k.startswith("_")}
    # datetime → isoformat
    for k, v in list(d.items()):
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d


# ---------------------------------------------------------------------------
# 엔드포인트
# ---------------------------------------------------------------------------
@router.get(
    "/sources",
    summary="화이트리스트 출처 목록",
    description="domain / type / minTrust / isWhitelisted 쿼리 필터 지원.",
)
async def list_sources(
    domain: str | None = Query(None, description="domains 배열에 포함 여부"),
    type: str | None = Query(None),
    minTrust: int = Query(0, ge=0, le=100),
    isWhitelisted: bool | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: str = Depends(require_user),
) -> dict:
    prisma = await _get_prisma()
    where: dict[str, Any] = {"trustLevel": {"gte": minTrust}}
    if type:
        where["type"] = type
    if isWhitelisted is not None:
        where["isWhitelisted"] = isWhitelisted
    if domain:
        where["domains"] = {"has": domain}

    rows = await prisma.trustedsource.find_many(
        where=where,
        order={"trustLevel": "desc"},
        take=limit,
        skip=offset,
    )
    total = await prisma.trustedsource.count(where=where)
    return {
        "total": total,
        "items": [_row_to_dict(r) for r in rows],
    }


@router.post(
    "/sources",
    summary="신규 화이트리스트 출처 등록",
    description="관리자 전용. domain 은 unique.",
)
async def create_source(body: SourceCreate, _: str = Depends(require_admin)) -> dict:
    prisma = await _get_prisma()
    try:
        created = await prisma.trustedsource.create(
            data=body.model_dump(exclude_none=True)
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _row_to_dict(created)


@router.put(
    "/sources/{source_id}",
    summary="출처 수정",
    description="trustLevel / isWhitelisted / 크롤 설정 등 변경. 관리자 전용.",
)
async def update_source(
    source_id: str,
    body: SourceUpdate,
    _: str = Depends(require_admin),
) -> dict:
    prisma = await _get_prisma()
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="no fields to update")
    try:
        updated = await prisma.trustedsource.update(
            where={"id": source_id},
            data=data,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _row_to_dict(updated)


@router.delete(
    "/sources/{source_id}",
    summary="출처 삭제",
    description="연관 SourceCitation 도 cascade 삭제. 관리자 전용.",
)
async def delete_source(source_id: str, _: str = Depends(require_admin)) -> dict:
    prisma = await _get_prisma()
    try:
        await prisma.trustedsource.delete(where={"id": source_id})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": source_id}


@router.post(
    "/sources/{source_id}/crawl",
    summary="즉시 크롤 트리거",
    description="테스트/관리자용. 결과 통계 즉시 반환.",
)
async def trigger_crawl(source_id: str, _: str = Depends(require_admin)) -> dict:
    try:
        return await crawl_one_source(source_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/sources/{source_id}/stats",
    summary="출처 통계",
    description="총 크롤 수 / 사실 수 / 성공률 / 마지막 크롤 시각 + 최근 시테이션.",
)
async def source_stats(source_id: str, _: str = Depends(require_user)) -> dict:
    prisma = await _get_prisma()
    src = await prisma.trustedsource.find_unique(where={"id": source_id})
    if not src:
        raise HTTPException(status_code=404, detail="source not found")
    recent = await prisma.sourcecitation.find_many(
        where={"sourceId": source_id},
        order={"crawledAt": "desc"},
        take=10,
    )
    return {
        "source": _row_to_dict(src),
        "recent_citations": [
            {
                "url": c.url,
                "title": c.title,
                "crawledAt": c.crawledAt.isoformat() if c.crawledAt else None,
                "publishedAt": c.publishedAt.isoformat() if c.publishedAt else None,
            }
            for c in recent
        ],
    }


@router.post(
    "/verify",
    summary="주장 cross-verify",
    description="화이트리스트 출처들로 stance 분류 → 가중 합산 신뢰도 반환.",
)
async def verify(body: VerifyRequest, _: str = Depends(require_user)) -> dict:
    try:
        result = await verify_claim(
            body.claim, domain=body.domain, top_k=body.top_k
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("verify_claim failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result.to_dict()


__all__ = ["router"]
