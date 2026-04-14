"""Output Parser - LLM 출력을 구조화된 형태로 파싱.

LLM이 생성한 텍스트에서 코드, JSON, 마크다운, 리스트 등을 추출합니다.
"""

from __future__ import annotations

import json
import re
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ParsedOutput:
    raw: str
    text: str                      # 순수 텍스트
    code_blocks: list[dict]        # [{"language": "python", "code": "..."}]
    json_blocks: list[dict | list] # 파싱된 JSON 객체들
    lists: list[list[str]]         # 불릿/번호 리스트
    citations: list[str]           # 출처 인용 [1], [문서 2] 등
    has_error: bool = False


class OutputParser:
    """LLM 출력 파서."""

    @staticmethod
    def parse(text: str) -> ParsedOutput:
        """전체 파싱."""
        code_blocks = OutputParser.extract_code_blocks(text)
        json_blocks = OutputParser.extract_json(text)
        lists = OutputParser.extract_lists(text)
        citations = OutputParser.extract_citations(text)

        # 코드 블록 제거한 순수 텍스트
        clean = re.sub(r"```[\s\S]*?```", "", text).strip()

        return ParsedOutput(
            raw=text, text=clean,
            code_blocks=code_blocks, json_blocks=json_blocks,
            lists=lists, citations=citations,
        )

    @staticmethod
    def extract_code_blocks(text: str) -> list[dict]:
        """코드 블록 추출."""
        pattern = r"```(\w*)\n([\s\S]*?)```"
        blocks = []
        for match in re.finditer(pattern, text):
            blocks.append({
                "language": match.group(1) or "text",
                "code": match.group(2).strip(),
            })
        return blocks

    @staticmethod
    def extract_json(text: str) -> list[dict | list]:
        """JSON 객체 추출."""
        results = []
        # ```json 블록
        for match in re.finditer(r"```json\s*\n?(.*?)\n?```", text, re.DOTALL):
            try:
                results.append(json.loads(match.group(1)))
            except json.JSONDecodeError:
                pass
        # 인라인 JSON
        for match in re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text):
            try:
                results.append(json.loads(match.group()))
            except json.JSONDecodeError:
                pass
        return results

    @staticmethod
    def extract_lists(text: str) -> list[list[str]]:
        """불릿/번호 리스트 추출."""
        lists = []
        current = []
        for line in text.split("\n"):
            line = line.strip()
            if re.match(r"^[-*•]\s+", line) or re.match(r"^\d+[.)]\s+", line):
                item = re.sub(r"^[-*•\d.)\s]+", "", line).strip()
                current.append(item)
            else:
                if current:
                    lists.append(current)
                    current = []
        if current:
            lists.append(current)
        return lists

    @staticmethod
    def extract_citations(text: str) -> list[str]:
        """출처 인용 추출. [1], [문서 2], [민법 제103조] 등."""
        return re.findall(r'\[([^\]]+)\]', text)
