"""Hwarang Protocol (HP) 라우터.

OpenAI 호환 `/v1/chat/completions` 외에 HP 전용 엔드포인트를 제공한다.

엔드포인트:
- POST /v1/hwarang/do      — DSL 단순 엔트리 (intent + scope + input → 자동 호출)
- POST /v1/hwarang/expand  — DSL → 확장된 system prompt (디버그)
- POST /v1/hwarang/parse   — Markup 응답 → 구조화 (디버그)

스펙: docs/hp-protocol.md §4
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from hwarang_api.protocol.dsl import (
    expand_intent_to_system_prompt,
    merge_into_messages,
)
from hwarang_api.protocol.markup import detect_identity, parse_markup
from hwarang_api.protocol.types import HwarangExtension, HwarangWorkflow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/hwarang", tags=["HwarangProtocol"])


# 내부 chat 호출 URL (기본: 로컬 8000) — 환경변수로 오버라이드 가능
def _chat_url() -> str:
    return os.getenv(
        "HWARANG_CHAT_URL", "http://localhost:8000/v1/chat/completions"
    )


def _build_workflow_from_request(raw: Any) -> HwarangWorkflow | None:
    """`/do` 요청의 `workflow` 필드를 HwarangWorkflow 로 정규화.

    허용 형태:
    - None
    - list[str]   → steps=[{name: s} for s in list]
    - list[dict]  → steps=list[dict]
    - dict        → 그대로 HwarangWorkflow 생성
    """
    if raw is None:
        return None
    if isinstance(raw, list):
        steps: list[dict] = []
        for s in raw:
            if isinstance(s, str):
                steps.append({"id": s, "name": s})
            elif isinstance(s, dict):
                steps.append(s)
        return HwarangWorkflow(steps=steps)
    if isinstance(raw, dict):
        try:
            return HwarangWorkflow(**raw)
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=f"workflow 검증 실패: {e}")
    raise HTTPException(status_code=400, detail="workflow 는 list 또는 dict 여야 합니다")


@router.post("/do")
async def hwarang_do(req: dict, request: Request) -> dict[str, Any]:
    """DSL 단순 엔트리.

    Request:
        {
          "intent": "add",
          "scope": "src/api/",
          "language": "ko",
          "input": "POST /api/orders 결제 후 주문 생성",
          "workflow": ["plan", "code", "test"]
        }

    내부에서 HP-Request 로 변환 후 `/v1/chat/completions` 호출.
    """
    intent = req.get("intent")
    if not intent:
        raise HTTPException(status_code=400, detail="intent 필수")

    user_input = req.get("input") or ""
    if not user_input:
        raise HTTPException(status_code=400, detail="input 필수")

    try:
        ext = HwarangExtension(
            intent=intent,
            scope=req.get("scope"),
            target=req.get("target"),
            language=req.get("language", "ko"),
            constraints=req.get("constraints", []) or [],
            style=req.get("style"),
            expertise=req.get("expertise"),
            format=req.get("format", "markup"),
            include=req.get("include", []) or [],
            workflow=_build_workflow_from_request(req.get("workflow")),
            identity=req.get("identity", "strict"),
            safety=req.get("safety", "standard"),
            workspace=req.get("workspace"),
        )
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"@hwarang 검증 실패: {e}")

    messages = [{"role": "user", "content": user_input}]
    messages = merge_into_messages(messages, ext)

    payload = {
        "model": req.get("model", "hwarang"),
        "messages": messages,
        "max_tokens": req.get("max_tokens", 16384),
        "temperature": req.get("temperature", 0.7),
        "@hwarang": ext.model_dump(),
    }

    # 내부 chat 호출
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(_chat_url(), json=payload)
    except httpx.HTTPError as e:
        logger.exception("내부 chat 호출 실패")
        raise HTTPException(status_code=502, detail=f"chat 호출 실패: {e}")

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    data = resp.json()
    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        or ""
    )
    markup = parse_markup(content)

    return {
        "ok": True,
        "summary": markup.get("summary") or "완료",
        "files_changed": [d["path"] for d in markup.get("diffs", [])],
        "next_steps": [s["title"] for s in markup.get("plan", []) if s.get("status") == "pending"],
        "@hwarang": data.get("@hwarang", {}),
        "raw_response": data,
    }


@router.post("/expand")
async def hwarang_expand(req: dict) -> dict[str, Any]:
    """DSL → 확장된 system prompt 텍스트 (디버그/검증용).

    Request body 가 그대로 `HwarangExtension` 으로 검증됨.
    """
    try:
        ext = HwarangExtension(**req)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"@hwarang 검증 실패: {e}")

    return {
        "system_prompt": expand_intent_to_system_prompt(ext),
        "extension": ext.model_dump(),
    }


@router.post("/parse")
async def hwarang_parse(req: dict) -> dict[str, Any]:
    """Markup 응답 텍스트 → 파싱된 섹션 (디버그/검증용).

    Request:
        {"content": "@@plan ... @@end ..."}
    """
    content = req.get("content", "") or ""
    markup = parse_markup(content)
    identity, confidence = detect_identity(content)
    return {
        "markup": markup,
        "identity": identity,
        "identity_confidence": confidence,
    }
