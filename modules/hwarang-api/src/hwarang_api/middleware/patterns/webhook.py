"""Webhook - 이벤트 발생 시 외부 서비스에 알림.

설정한 URL로 이벤트를 자동 전달합니다.
예: 토큰 소진 → 슬랙 알림, 작업 완료 → 외부 시스템 콜백
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WebhookConfig:
    url: str
    secret: str = ""           # HMAC 서명 키
    events: list[str] = None   # 구독할 이벤트 (None이면 전체)
    active: bool = True


class WebhookManager:
    """웹훅 관리 + 발송."""

    def __init__(self):
        self._webhooks: dict[str, WebhookConfig] = {}

    def register(self, webhook_id: str, config: WebhookConfig):
        self._webhooks[webhook_id] = config

    def unregister(self, webhook_id: str):
        self._webhooks.pop(webhook_id, None)

    async def dispatch(self, event_type: str, payload: dict):
        """이벤트를 구독한 모든 웹훅에 발송."""
        for wh_id, config in self._webhooks.items():
            if not config.active:
                continue
            if config.events and event_type not in config.events:
                continue

            asyncio.create_task(self._send(wh_id, config, event_type, payload))

    async def _send(self, wh_id: str, config: WebhookConfig,
                    event_type: str, payload: dict):
        body = {
            "event": event_type,
            "timestamp": time.time(),
            "data": payload,
        }
        body_str = json.dumps(body)

        headers = {"Content-Type": "application/json"}
        if config.secret:
            sig = hmac.new(config.secret.encode(), body_str.encode(), hashlib.sha256).hexdigest()
            headers["X-Hwarang-Signature"] = f"sha256={sig}"

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(config.url, data=body_str, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status >= 400:
                        logger.warning(f"Webhook {wh_id} 실패: {resp.status}")
        except Exception as e:
            logger.warning(f"Webhook {wh_id} 발송 오류: {e}")
