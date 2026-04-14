"""Function Calling / Tool Use - LLM이 함수를 호출하는 패턴.

LLM이 텍스트만 생성하는 게 아니라,
"이 함수를 이 인자로 호출해줘"라고 요청하면
시스템이 실제로 함수를 실행하고 결과를 돌려줍니다.

예시:
  사용자: "양도세 계산해줘, 8억에 사서 12억에 팔았어"
  LLM: → calculate_tax(purchase=800000000, sale=1200000000)
  시스템: → 함수 실행 → 결과: 세액 23,400,000원
  LLM: "양도차익 4억원에 대한 양도소득세는 약 2,340만원입니다"
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class FunctionDef:
    """함수 정의 (OpenAI function calling 호환)."""
    name: str
    description: str
    parameters: dict  # JSON Schema
    handler: Callable  # 실제 실행할 Python 함수


@dataclass
class FunctionCall:
    """LLM이 요청한 함수 호출."""
    name: str
    arguments: dict


@dataclass
class FunctionResult:
    """함수 실행 결과."""
    name: str
    result: Any
    success: bool
    error: str | None = None


class FunctionRegistry:
    """함수 등록 + 실행 관리."""

    def __init__(self):
        self._functions: dict[str, FunctionDef] = {}

    def register(self, func_def: FunctionDef):
        self._functions[func_def.name] = func_def

    def register_function(
        self, name: str, description: str, parameters: dict
    ) -> Callable:
        """데코레이터로 함수 등록."""
        def decorator(func: Callable) -> Callable:
            self._functions[name] = FunctionDef(
                name=name, description=description,
                parameters=parameters, handler=func,
            )
            return func
        return decorator

    def get_tool_definitions(self) -> list[dict]:
        """OpenAI 호환 tool definitions."""
        return [
            {
                "type": "function",
                "function": {
                    "name": f.name,
                    "description": f.description,
                    "parameters": f.parameters,
                },
            }
            for f in self._functions.values()
        ]

    async def execute(self, call: FunctionCall) -> FunctionResult:
        """함수 실행."""
        func_def = self._functions.get(call.name)
        if not func_def:
            return FunctionResult(name=call.name, result=None, success=False,
                                 error=f"Unknown function: {call.name}")
        try:
            import asyncio
            if asyncio.iscoroutinefunction(func_def.handler):
                result = await func_def.handler(**call.arguments)
            else:
                result = func_def.handler(**call.arguments)
            return FunctionResult(name=call.name, result=result, success=True)
        except Exception as e:
            return FunctionResult(name=call.name, result=None, success=False, error=str(e))

    def parse_function_call(self, response_text: str) -> FunctionCall | None:
        """LLM 응답에서 function call 파싱."""
        # JSON 블록에서 함수 호출 추출
        try:
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0]
            elif "{" in response_text:
                start = response_text.index("{")
                end = response_text.rindex("}") + 1
                json_str = response_text[start:end]
            else:
                return None

            data = json.loads(json_str)
            if "name" in data and "arguments" in data:
                return FunctionCall(name=data["name"], arguments=data["arguments"])
        except (json.JSONDecodeError, ValueError):
            pass
        return None
