"""Structured Output - JSON 모드.

LLM이 자유 텍스트가 아니라 구조화된 JSON을 출력하도록 강제합니다.

사용법:
    result = await engine.generate(request, json_schema={
        "type": "object",
        "properties": {
            "parties": {"type": "array", "items": {"type": "string"}},
            "amount": {"type": "number"},
            "date": {"type": "string"},
        },
        "required": ["parties", "amount"]
    })
"""

from __future__ import annotations

import json
import re
import logging

logger = logging.getLogger(__name__)


def extract_json(text: str) -> dict | list | None:
    """LLM 출력에서 JSON 추출."""
    # 1. ```json 블록
    match = re.search(r"```json\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 2. 순수 JSON
    text = text.strip()
    if text.startswith(("{", "[")):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # 3. 텍스트 안에 JSON 찾기
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == start_char:
                depth += 1
            elif text[i] == end_char:
                depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    break

    return None


def validate_json_schema(data: dict | list, schema: dict) -> tuple[bool, str]:
    """간단한 JSON Schema 검증."""
    try:
        schema_type = schema.get("type")
        if schema_type == "object" and not isinstance(data, dict):
            return False, f"Expected object, got {type(data).__name__}"
        if schema_type == "array" and not isinstance(data, list):
            return False, f"Expected array, got {type(data).__name__}"

        # required 필드 확인
        if schema_type == "object":
            required = schema.get("required", [])
            for field in required:
                if field not in data:
                    return False, f"Missing required field: {field}"

        return True, ""
    except Exception as e:
        return False, str(e)


def build_json_prompt(user_query: str, schema: dict) -> str:
    """JSON 출력을 유도하는 프롬프트 구성."""
    schema_str = json.dumps(schema, indent=2, ensure_ascii=False)
    return (
        f"{user_query}\n\n"
        f"반드시 아래 JSON 스키마에 맞는 JSON만 출력하세요. "
        f"다른 텍스트 없이 JSON만:\n\n"
        f"```json\n{schema_str}\n```"
    )
