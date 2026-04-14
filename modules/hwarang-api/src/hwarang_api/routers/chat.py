"""Chat completions endpoint - OpenAI compatible.

Supports two modes:
1. Local mode: API server has the model loaded in-process (single server)
2. Distributed mode: API server delegates to Worker nodes via Redis (multi server)

Mode is determined by whether a LoadBalancer is configured.
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

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

router = APIRouter()


@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request_body: ChatCompletionRequest, request: Request):
    """Create a chat completion.

    Compatible with the OpenAI /v1/chat/completions endpoint.
    Automatically routes to local engine or distributed workers.
    """
    # Check if distributed mode is available
    load_balancer = getattr(request.app.state, "load_balancer", None)

    if load_balancer:
        return await _distributed_chat(request_body, load_balancer)
    else:
        return await _local_chat(request_body, request)


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
