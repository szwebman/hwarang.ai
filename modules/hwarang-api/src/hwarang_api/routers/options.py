"""옵션 제시 모드 API.

엔드포인트:
- POST /api/options/detect    : 메시지 → 옵션 모드 필요 여부
- POST /api/options/generate  : 옵션 2~4개 생성 (LLM + 정적 fallback)
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from hwarang_api.knowledge.option_detector import detect_option_intent
from hwarang_api.knowledge.option_generator import generate_options
from hwarang_api.routers.learning import _check_internal_key

router = APIRouter(prefix="/api/options", tags=["options"])


def _require(authorization: Optional[str] = Header(None)) -> None:
    _check_internal_key(authorization)


class DetectRequest(BaseModel):
    message: str
    has_image: bool = False


class GenerateRequest(BaseModel):
    message: str
    deliverable: str
    has_image: bool = False
    image_description: Optional[str] = None


@router.post("/detect")
async def detect(req: DetectRequest, _: None = Depends(_require)):
    intent = detect_option_intent(req.message, has_image=req.has_image)
    return {
        "needs_options": intent.needs_options,
        "confidence": intent.confidence,
        "deliverable": intent.deliverable,
        "reason": intent.reason,
    }


@router.post("/generate")
async def generate(req: GenerateRequest, _: None = Depends(_require)):
    options = await generate_options(
        user_message=req.message,
        deliverable=req.deliverable,
        has_image=req.has_image,
        image_description=req.image_description,
    )
    return {
        "options": [
            {
                "id": o.id,
                "title": o.title,
                "description": o.description,
                "keywords": o.keywords,
                "preview_emoji": o.preview_emoji,
            }
            for o in options
        ],
    }
