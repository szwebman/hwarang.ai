"""자체개선(Self-Modify) 라우터.

모든 엔드포인트는 관리자 인증 필수.
PR 생성은 환경변수 HWARANG_SELF_MODIFY_ENABLED=1 가 있어야 동작.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from hwarang_api.cognitive.self_modify import recent_proposals
from hwarang_api.cognitive.self_modify.__main__ import propose_change

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/self-modify", tags=["SelfModify"])


# TODO: 가능하면 hwarang_api.middleware.auth 의 관리자 미들웨어로 교체.
# 현재는 X-Admin-Token 헤더를 HWARANG_ADMIN_TOKEN 환경변수와 비교한다.
def _verify_admin(x_admin_token: Optional[str]) -> None:
    expected = os.getenv("HWARANG_ADMIN_TOKEN")
    if not expected:
        # 토큰이 설정되지 않았으면 안전하게 거부
        raise HTTPException(
            status_code=503,
            detail="HWARANG_ADMIN_TOKEN 미설정 — 자체개선 API 사용 불가",
        )
    if not x_admin_token or x_admin_token != expected:
        raise HTTPException(status_code=401, detail="관리자 인증 실패")


class ProposeRequest(BaseModel):
    file_path: str = Field(..., description="대상 파일 (repo 루트 기준 상대 경로)")
    observation: str = Field(..., description="관찰된 문제 설명")
    test_command: str = Field("pytest -x -q", description="샌드박스 내부 실행 명령")


class DryRunRequest(BaseModel):
    file_path: str
    observation: str
    test_command: str = "pytest -x -q"


def _get_llm(request: Request) -> Any:
    """앱 상태에서 LLM 핸들을 얻는다.

    ModelManager 가 generate(prompt) 같은 호출을 지원한다고 가정하고,
    어댑터를 노출. 실패 시 503.
    """
    mm = getattr(request.app.state, "model_manager", None)
    if mm is None:
        raise HTTPException(status_code=503, detail="model_manager unavailable")

    # ModelManager 의 generate 시그니처에 의존하지 않게 단순 프록시 어댑터 사용.
    class _LLMAdapter:
        def __init__(self, manager: Any):
            self._m = manager

        def generate(self, prompt: str) -> str:
            # 동기 fallback — manager 가 비동기여도 다양한 시그니처 시도
            for attr in ("generate_sync", "complete", "generate"):
                fn = getattr(self._m, attr, None)
                if callable(fn):
                    try:
                        result = fn(prompt)
                        if hasattr(result, "__await__"):
                            # 자체개선 API 는 동기 호출만 허용 — 비동기는 미지원
                            raise RuntimeError(
                                f"{attr} 가 코루틴 반환 — 동기 LLM 인터페이스 필요"
                            )
                        return str(result)
                    except RuntimeError:
                        raise
                    except Exception as e:
                        logger.warning(f"LLM {attr} 호출 실패: {e}")
                        continue
            raise RuntimeError("LLM 동기 호출 인터페이스 없음")

    return _LLMAdapter(mm)


@router.post("/propose")
async def propose(
    body: ProposeRequest,
    request: Request,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> dict[str, Any]:
    """전체 파이프라인 실행: 제안 → 샌드박스 → 게이트 → Draft PR."""
    _verify_admin(x_admin_token)
    llm = _get_llm(request)
    result = propose_change(
        file_path=body.file_path,
        observation=body.observation,
        llm=llm,
        test_command=body.test_command,
        create_pr=True,
    )
    return result


@router.post("/dry-run")
async def dry_run(
    body: DryRunRequest,
    request: Request,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> dict[str, Any]:
    """제안 + 샌드박스 + 검증만, PR 은 절대 생성하지 않음."""
    _verify_admin(x_admin_token)
    llm = _get_llm(request)
    result = propose_change(
        file_path=body.file_path,
        observation=body.observation,
        llm=llm,
        test_command=body.test_command,
        create_pr=False,
    )
    return result


@router.get("/audit")
async def audit(
    n: int = 20,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> dict[str, Any]:
    """최근 자체개선 제안 감사 로그."""
    _verify_admin(x_admin_token)
    n = max(1, min(n, 200))
    return {"proposals": recent_proposals(n)}
