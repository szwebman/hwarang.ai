"""Chat completions endpoint - OpenAI compatible.

Supports two modes:
1. Local mode: API server has the model loaded in-process (single server)
2. Distributed mode: API server delegates to Worker nodes via Redis (multi server)

Mode is determined by whether a LoadBalancer is configured.

Hwarang Protocol (HP) 통합:
- 요청 본문에 `@hwarang` 필드가 있으면 추출하여 system prompt 보강 + 응답에 메타 추가
- `@hwarang` 가 없으면 OpenAI 표준 그대로 동작 (100% backward compat)
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from hwarang_shared.schemas.chat import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    ChunkChoice,
    DeltaContent,
    Role,
    Usage,
)

from hwarang_api.protocol.dsl import (
    estimate_tokens_saved,
    merge_into_messages,
)
from hwarang_api.protocol.markup import detect_identity, parse_markup
from hwarang_api.protocol.types import HwarangExtension

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat/completions")
async def chat_completions(request: Request):
    """Create a chat completion.

    Compatible with the OpenAI /v1/chat/completions endpoint.
    Automatically routes to local engine or distributed workers.

    `@hwarang` 확장 필드가 있으면 HP 프로토콜로 처리하고, 없으면 OpenAI 표준 그대로.
    """
    try:
        raw_body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"JSON 파싱 실패: {e}")

    if not isinstance(raw_body, dict):
        raise HTTPException(status_code=400, detail="요청 본문은 JSON 객체여야 합니다")

    # ── HP 확장 추출 (vLLM 으로 보내기 전 분리) ──
    hwarang_ext_raw = raw_body.pop("@hwarang", None)
    hwarang_ext: HwarangExtension | None = None
    if hwarang_ext_raw is not None:
        if not isinstance(hwarang_ext_raw, dict):
            raise HTTPException(
                status_code=400, detail="`@hwarang` 는 객체(dict)여야 합니다"
            )
        try:
            hwarang_ext = HwarangExtension(**hwarang_ext_raw)
        except ValidationError as e:
            raise HTTPException(
                status_code=400, detail=f"`@hwarang` 검증 실패: {e}"
            )

        # DSL 보강을 messages 에 prepend
        if "messages" in raw_body and isinstance(raw_body["messages"], list):
            raw_body["messages"] = merge_into_messages(raw_body["messages"], hwarang_ext)

    # ── OpenAI 표준 검증 ──
    try:
        request_body = ChatCompletionRequest(**raw_body)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Check if distributed mode is available
    load_balancer = getattr(request.app.state, "load_balancer", None)

    if load_balancer:
        response = await _distributed_chat(request_body, load_balancer)
    else:
        response = await _local_chat(request_body, request)

    # ── HP 응답 보강 (스트리밍이 아닌 경우만) ──
    # 스트리밍은 StreamingResponse 라 그대로 반환
    if isinstance(response, StreamingResponse):
        return response

    if hwarang_ext is None:
        return response

    return _enrich_with_hwarang(response, hwarang_ext)


def _enrich_with_hwarang(
    response: ChatCompletionResponse, ext: HwarangExtension
) -> JSONResponse:
    """Non-streaming 응답에 `@hwarang` 메타 추가.

    OpenAI 호환 필드는 그대로 유지하고 최상위 `@hwarang` 키만 추가.
    """
    # Pydantic 모델 → dict
    body = response.model_dump(mode="json")

    # 첫 choice 의 content 분석
    content = ""
    tool_calls: list[dict] = []
    try:
        first_choice = body["choices"][0]
        msg = first_choice.get("message") or {}
        content = msg.get("content") or ""
        tool_calls = msg.get("tool_calls") or []
    except (IndexError, KeyError):
        pass

    markup = parse_markup(content) if ext.format == "markup" else None
    identity, confidence = detect_identity(content)

    body["@hwarang"] = {
        "format_used": ext.format,
        "lora_used": "v7",
        "identity": identity,
        "identity_confidence": confidence,
        "markup": markup,
        "tool_calls_meta": [
            {
                "id": tc.get("id"),
                "name": (tc.get("function") or {}).get("name"),
                "risk": "low",
                "auto_approved": True,
            }
            for tc in tool_calls
        ],
        "workflow": (
            {
                "name": ext.workflow.name,
                "on_fail": ext.workflow.on_fail,
            }
            if ext.workflow
            else None
        ),
        "telemetry": {
            "tokens_saved_by_dsl": estimate_tokens_saved(ext),
            "tools_used": [(tc.get("function") or {}).get("name") for tc in tool_calls],
            "fallback_count": 0,
        },
    }

    return JSONResponse(
        content=body,
        headers={"X-Hwarang-Protocol": "1.0"},
    )


async def _local_chat(request_body: ChatCompletionRequest, request: Request):
    """Handle request with local in-process model."""
    model_manager = request.app.state.model_manager

    try:
        engine = model_manager.get_engine(request_body.model)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if request_body.stream:
        return StreamingResponse(
            _local_stream(engine, request_body),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Hwarang-Protocol": "1.0",
            },
        )

    return await engine.generate(request_body)


async def _local_stream(engine, request: ChatCompletionRequest):
    """Generate SSE stream from local engine."""
    async for chunk in engine.generate_stream(request):
        yield f"data: {chunk.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"


async def _distributed_chat(request_body: ChatCompletionRequest, load_balancer):
    """Handle request by distributing to worker nodes."""
    from hwarang_api.distributed.protocol import InferenceRequest

    # Convert to internal request
    inf_request = InferenceRequest(
        model=request_body.model,
        messages=[
            {"role": m.role.value, "content": m.content or ""}
            for m in request_body.messages
        ],
        temperature=request_body.temperature,
        top_p=request_body.top_p,
        max_tokens=request_body.max_tokens or 512,
        stream=request_body.stream,
    )

    if request_body.stream:
        return StreamingResponse(
            _distributed_stream(inf_request, load_balancer, request_body.model),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Hwarang-Protocol": "1.0",
            },
        )

    # Non-streaming: submit and wait
    response = await load_balancer.submit_request(inf_request)

    if not response.success:
        raise HTTPException(status_code=503, detail=response.error)

    return ChatCompletionResponse(
        model=request_body.model,
        choices=[
            Choice(
                index=0,
                message=ChatMessage(role=Role.ASSISTANT, content=response.content),
                finish_reason=response.finish_reason,
            )
        ],
        usage=Usage(
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.prompt_tokens + response.completion_tokens,
        ),
    )


async def _distributed_stream(inf_request, load_balancer, model: str):
    """Generate SSE stream from distributed worker."""
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    # First chunk: role
    first = ChatCompletionChunk(
        id=chunk_id,
        created=created,
        model=model,
        choices=[ChunkChoice(index=0, delta=DeltaContent(role=Role.ASSISTANT))],
    )
    yield f"data: {first.model_dump_json()}\n\n"

    # Stream chunks from worker
    async for worker_chunk in load_balancer.submit_stream(inf_request):
        if worker_chunk.finish_reason == "error":
            break

        chunk = ChatCompletionChunk(
            id=chunk_id,
            created=created,
            model=model,
            choices=[
                ChunkChoice(
                    index=0,
                    delta=DeltaContent(content=worker_chunk.content if not worker_chunk.finish_reason else None),
                    finish_reason=worker_chunk.finish_reason,
                )
            ],
        )
        yield f"data: {chunk.model_dump_json()}\n\n"

        if worker_chunk.finish_reason:
            break

    yield "data: [DONE]\n\n"
