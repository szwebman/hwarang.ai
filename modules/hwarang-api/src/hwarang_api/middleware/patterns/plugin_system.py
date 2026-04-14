"""Plugin System - 외부 도구 연결.

슬랙, 노션, 구글독스, GitHub 등 외부 서비스를 플러그인으로 연결합니다.

예시:
  사용자: "이 코드 리뷰 결과를 슬랙 #dev-review 채널에 보내줘"
  → LLM이 slack_send 플러그인 호출
  → 슬랙에 메시지 전송
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PluginInfo:
    name: str
    description: str
    version: str
    author: str
    enabled: bool = True


class Plugin(ABC):
    """플러그인 베이스 클래스."""

    @abstractmethod
    def get_info(self) -> PluginInfo: ...

    @abstractmethod
    def get_tools(self) -> list[dict]:
        """이 플러그인이 제공하는 도구 목록 (OpenAI function calling 형식)."""
        ...

    @abstractmethod
    async def execute(self, tool_name: str, arguments: dict) -> Any: ...


class PluginManager:
    """플러그인 관리."""

    def __init__(self):
        self._plugins: dict[str, Plugin] = {}

    def register(self, plugin: Plugin):
        info = plugin.get_info()
        self._plugins[info.name] = plugin
        logger.info(f"플러그인 등록: {info.name} v{info.version}")

    def unregister(self, name: str):
        self._plugins.pop(name, None)

    def get_all_tools(self) -> list[dict]:
        """모든 플러그인의 도구 통합."""
        tools = []
        for plugin in self._plugins.values():
            if plugin.get_info().enabled:
                tools.extend(plugin.get_tools())
        return tools

    async def execute(self, tool_name: str, arguments: dict) -> Any:
        """도구 이름으로 실행 (어떤 플러그인인지 자동 라우팅)."""
        for plugin in self._plugins.values():
            tool_names = [t["function"]["name"] for t in plugin.get_tools()]
            if tool_name in tool_names:
                return await plugin.execute(tool_name, arguments)
        raise ValueError(f"Unknown tool: {tool_name}")

    @property
    def list_plugins(self) -> list[PluginInfo]:
        return [p.get_info() for p in self._plugins.values()]


# ============================================================
# 기본 제공 플러그인 예시
# ============================================================

class SlackPlugin(Plugin):
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def get_info(self) -> PluginInfo:
        return PluginInfo(name="slack", description="슬랙 메시지 전송",
                         version="1.0", author="hwarang")

    def get_tools(self) -> list[dict]:
        return [{
            "type": "function",
            "function": {
                "name": "slack_send",
                "description": "슬랙 채널에 메시지 전송",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "channel": {"type": "string"},
                        "message": {"type": "string"},
                    },
                    "required": ["message"],
                },
            },
        }]

    async def execute(self, tool_name: str, arguments: dict) -> Any:
        if tool_name == "slack_send":
            import aiohttp
            async with aiohttp.ClientSession() as session:
                await session.post(self.webhook_url, json={"text": arguments["message"]})
            return {"status": "sent", "channel": arguments.get("channel", "#general")}


class WebSearchPlugin(Plugin):
    def get_info(self) -> PluginInfo:
        return PluginInfo(name="web_search", description="웹 검색",
                         version="1.0", author="hwarang")

    def get_tools(self) -> list[dict]:
        return [{
            "type": "function",
            "function": {
                "name": "search_web",
                "description": "웹에서 최신 정보 검색",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "검색어"},
                    },
                    "required": ["query"],
                },
            },
        }]

    async def execute(self, tool_name: str, arguments: dict) -> Any:
        # TODO: 실제 검색 API 연동 (Google/Bing/Serper)
        return {"results": [f"검색 결과: {arguments['query']}"]}
