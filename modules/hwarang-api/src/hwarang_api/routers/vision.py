"""VLM 라우터 — 이미지 → 시각 description.

화랑 Vision-to-Code 파이프라인:
    1. Next.js (chat/route.ts) 가 이미지 base64 와 사용자 instruction 을 보냄
    2. 이 라우터가 별도 vLLM 인스턴스 (Qwen2.5-VL, 기본 포트 8002) 의
       OpenAI 호환 ``/v1/chat/completions`` 멀티모달 API 를 호출
    3. 결과 description 을 Next.js 로 반환 → system prompt 로 주입 후 코더 LLM 호출

환경변수:
    HWARANG_VLM_URL   기본 ``http://localhost:8002`` — VLM vLLM 서버 base URL
    HWARANG_VLM_MODEL 기본 ``hwarang-vl`` — ``--served-model-name`` 과 일치해야 함
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from hwarang_api.routers.learning import _check_internal_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vision", tags=["Vision/VLM"])


VLM_URL = os.getenv("HWARANG_VLM_URL", "http://localhost:8002")
VLM_MODEL = os.getenv("HWARANG_VLM_MODEL", "hwarang-vl")

# 한 번에 분석할 최대 이미지 수 (VLM 컨텍스트 + 비용 제한)
MAX_IMAGES = 4
# 최대 응답 토큰
VLM_MAX_TOKENS = 2000


def _require_internal_key(authorization: Optional[str] = Header(None)) -> None:
    """내부 호출 전용. ``HWARANG_INTERNAL_KEY`` 검증."""
    return _check_internal_key(authorization)


class AnalyzeRequest(BaseModel):
    images: list[str] = Field(
        default_factory=list,
        description="data URL 배열 (data:image/png;base64,... 형식). 최대 4장.",
    )
    instruction: Optional[str] = Field(
        default=None,
        description="사용자 요청 컨텍스트. '코드/구현/만들어' 등 키워드 시 코드 명세 모드로 자동 전환.",
    )


VLM_PROMPT_GENERAL = """이 이미지를 분석해서 다음 항목을 한국어로 자세히 설명해라:
1. 레이아웃 (hero / grid / split / sidebar 등)
2. 색상 팔레트 (주요 색 3~5개, 가능하면 hex)
3. 타이포그래피 (제목/본문 스타일)
4. 주요 컴포넌트 (button, card, form 등)
5. 시각적 분위기 (minimalism, brutalism 등)

코드 생성용 description 으로 사용될 것. 구체적으로:"""


VLM_PROMPT_CODE = """이 디자인을 React + TailwindCSS 로 구현하기 위한 상세 명세를 작성해라.

포함:
- 컴포넌트 트리 (Hero, Card, Footer 등)
- 각 요소의 위치 / 크기
- 색상 hex 값
- 폰트 크기 / 무게
- 간격 (padding, margin)
- 인터랙션 힌트 (hover, click)

상세 명세:"""


_CODE_KEYWORDS = (
    "코드", "구현", "만들어", "짜줘", "구현해", "리액트", "react",
    "html", "css", "tailwind", "code", "build", "develop", "vue", "next",
)


def _is_code_request(instruction: Optional[str]) -> bool:
    if not instruction:
        return False
    low = instruction.lower()
    return any(k in low for k in _CODE_KEYWORDS)


@router.post("/analyze")
async def analyze(
    req: AnalyzeRequest,
    _: bool = Depends(_require_internal_key),
):
    """이미지 → VLM 분석 → 자연어 description.

    실패 시에도 200 + ``error`` 필드 (Next.js 가 fallback 처리하기 쉽도록).
    """
    if not req.images:
        return {"error": "no_images", "description": "", "image_count": 0}

    is_code = _is_code_request(req.instruction)
    prompt = VLM_PROMPT_CODE if is_code else VLM_PROMPT_GENERAL

    # OpenAI 호환 multimodal request — vLLM 의 Qwen2.5-VL 도 동일 스키마
    images = req.images[:MAX_IMAGES]
    user_content: list[dict] = [{"type": "text", "text": prompt}]
    user_content.extend(
        {"type": "image_url", "image_url": {"url": img}} for img in images
    )
    messages = [{"role": "user", "content": user_content}]

    payload = {
        "model": VLM_MODEL,
        "messages": messages,
        "max_tokens": VLM_MAX_TOKENS,
        "temperature": 0.3,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{VLM_URL}/v1/chat/completions",
                json=payload,
            )
        if resp.status_code != 200:
            logger.warning("VLM 응답 실패 status=%s body=%s", resp.status_code, resp.text[:300])
            return {
                "error": "vlm_failed",
                "detail": resp.text[:300],
                "description": "",
                "image_count": len(images),
                "fallback": "VLM 서버 응답 실패. 이미지 분석 불가.",
            }

        data = resp.json()
        description = (
            data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
        ).strip()

        return {
            "description": description,
            "image_count": len(images),
            "mode": "code" if is_code else "general",
            "model": VLM_MODEL,
        }
    except httpx.TimeoutException:
        logger.warning("VLM 호출 타임아웃")
        return {
            "error": "vlm_timeout",
            "description": "",
            "image_count": len(images),
            "fallback": "VLM 응답 시간 초과. 이미지 없이 답변합니다.",
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("VLM 호출 실패: %s", e)
        return {
            "error": "vlm_unavailable",
            "detail": str(e),
            "description": "",
            "image_count": len(images),
            "fallback": "VLM 서버에 연결할 수 없습니다. 이미지 없이 답변합니다.",
        }


@router.get("/health")
async def health():
    """VLM 서버 상태 헬스 체크.

    설정된 ``HWARANG_VLM_URL`` 의 ``/v1/models`` 응답으로 서빙 여부 확인.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{VLM_URL}/v1/models")
        ok = resp.status_code == 200
        models: list = []
        if ok:
            try:
                models = resp.json().get("data", [])
            except Exception:  # noqa: BLE001
                models = []
        return {
            "url": VLM_URL,
            "configured": True,
            "ok": ok,
            "model_name": VLM_MODEL,
            "models": models,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "url": VLM_URL,
            "configured": True,
            "ok": False,
            "model_name": VLM_MODEL,
            "error": str(e),
        }
