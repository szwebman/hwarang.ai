"""Streaming Protocol - SSE + WebSocket 통합 스트리밍.

SSE (Server-Sent Events): HTTP 기반, 단방향 (서버→클라이언트)
WebSocket: 양방향, 실시간 대화

사용 시나리오:
  SSE → API 호출 (OpenAI 호환, /v1/chat/completions?stream=true)
  WebSocket → 웹 채팅 UI (양방향, 타이핑 표시, 중단 버튼)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator

logger = logging.getLogger(__name__)


class SSEFormatter:
    """Server-Sent Events 포맷터."""

    @staticmethod
    def format_chunk(data: dict) -> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    @staticmethod
    def format_done() -> str:
        return "data: [DONE]\n\n"

    @staticmethod
    def format_error(error: str) -> str:
        return f"data: {json.dumps({'error': error})}\n\n"

    @staticmethod
    async def stream_response(chunks: AsyncIterator[dict]) -> AsyncIterator[str]:
        """청크 이터레이터 → SSE 문자열 이터레이터."""
        async for chunk in chunks:
            yield SSEFormatter.format_chunk(chunk)
        yield SSEFormatter.format_done()


class WebSocketHandler:
    """WebSocket 채팅 핸들러.

    양방향 통신:
    - 클라이언트 → 서버: 메시지, 중단 요청, 타이핑 상태
    - 서버 → 클라이언트: 스트리밍 응답, 상태 업데이트
    """

    def __init__(self, agent_loop):
        self.agent = agent_loop
        self._active_tasks: dict[str, asyncio.Task] = {}

    async def handle(self, websocket, user_id: str):
        """WebSocket 연결 처리."""
        logger.info(f"WS connected: {user_id}")
        try:
            async for raw in websocket:
                msg = json.loads(raw)
                msg_type = msg.get("type")

                if msg_type == "message":
                    task = asyncio.create_task(
                        self._process_message(websocket, user_id, msg)
                    )
                    self._active_tasks[user_id] = task

                elif msg_type == "stop":
                    # 중단 요청
                    task = self._active_tasks.get(user_id)
                    if task:
                        task.cancel()
                        await websocket.send(json.dumps({"type": "stopped"}))

                elif msg_type == "typing":
                    pass  # 타이핑 상태 (다른 사용자에게 전달 가능)

        except Exception as e:
            logger.warning(f"WS error: {e}")
        finally:
            self._active_tasks.pop(user_id, None)
            logger.info(f"WS disconnected: {user_id}")

    async def _process_message(self, websocket, user_id: str, msg: dict):
        """메시지 처리 + 스트리밍 응답."""
        text = msg.get("content", "")
        try:
            await websocket.send(json.dumps({"type": "start"}))

            async for chunk in self.agent.stream_response(text):
                await websocket.send(json.dumps({
                    "type": "chunk", "content": chunk,
                }))

            await websocket.send(json.dumps({"type": "done"}))
        except asyncio.CancelledError:
            await websocket.send(json.dumps({"type": "stopped"}))
