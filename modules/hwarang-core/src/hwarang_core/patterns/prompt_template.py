"""Prompt Template - 도메인별 프롬프트 관리.

프롬프트를 하드코딩하지 않고 템플릿으로 관리합니다.
버전 관리, A/B 테스트, 도메인별 분리 가능.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PromptTemplate:
    id: str
    name: str
    domain: str                   # "code", "legal", "tax", "general"
    version: str = "1.0"
    system_prompt: str = ""
    user_template: str = ""       # {query}, {context} 등 변수 포함
    variables: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def render(self, **kwargs) -> list[dict]:
        """템플릿에 변수를 채워서 메시지 리스트 반환."""
        messages = []
        if self.system_prompt:
            system = self.system_prompt
            for key, value in kwargs.items():
                system = system.replace(f"{{{key}}}", str(value))
            messages.append({"role": "system", "content": system})

        if self.user_template:
            user = self.user_template
            for key, value in kwargs.items():
                user = user.replace(f"{{{key}}}", str(value))
            messages.append({"role": "user", "content": user})

        return messages


class PromptManager:
    """프롬프트 템플릿 관리."""

    def __init__(self):
        self._templates: dict[str, PromptTemplate] = {}
        self._register_defaults()

    def register(self, template: PromptTemplate):
        self._templates[template.id] = template

    def get(self, template_id: str) -> PromptTemplate | None:
        return self._templates.get(template_id)

    def get_by_domain(self, domain: str) -> list[PromptTemplate]:
        return [t for t in self._templates.values() if t.domain == domain]

    def render(self, template_id: str, **kwargs) -> list[dict]:
        t = self._templates.get(template_id)
        if not t:
            raise ValueError(f"Template not found: {template_id}")
        return t.render(**kwargs)

    def _register_defaults(self):
        """기본 프롬프트 등록."""
        defaults = [
            PromptTemplate(
                id="code_general", name="코딩 일반", domain="code",
                system_prompt="당신은 한국어 코딩 전문 AI입니다. 한국어 주석과 설명을 자연스럽게 작성합니다.",
                user_template="{query}",
            ),
            PromptTemplate(
                id="code_review", name="코드 리뷰", domain="code",
                system_prompt="당신은 시니어 개발자입니다. 코드를 리뷰하고 개선점을 제안합니다.",
                user_template="다음 코드를 리뷰해주세요:\n\n```{language}\n{code}\n```",
                variables=["language", "code"],
            ),
            PromptTemplate(
                id="legal_qa", name="법률 QA", domain="legal",
                system_prompt=(
                    "당신은 한국 법률 전문 AI입니다.\n"
                    "반드시 제공된 문서를 기반으로 답변하고, 출처를 표시하세요.\n"
                    "확실하지 않은 내용은 '확인이 필요합니다'라고 답하세요."
                ),
                user_template="참고 문서:\n{context}\n\n질문: {query}",
                variables=["context", "query"],
            ),
            PromptTemplate(
                id="tax_calc", name="세무 계산", domain="tax",
                system_prompt=(
                    "당신은 한국 세무 전문 AI입니다.\n"
                    "세법에 근거하여 단계별로 계산합니다.\n"
                    "계산 결과에는 반드시 관련 법령 조항을 인용하세요."
                ),
                user_template="참고 세법:\n{context}\n\n질문: {query}",
                variables=["context", "query"],
            ),
            PromptTemplate(
                id="rag_general", name="RAG 일반", domain="general",
                system_prompt=(
                    "제공된 문서를 기반으로 정확하게 답변하세요.\n"
                    "문서에 없는 내용은 답하지 마세요.\n"
                    "답변 시 출처 [문서 N]을 표시하세요."
                ),
                user_template="참고 문서:\n{context}\n\n질문: {query}",
                variables=["context", "query"],
            ),
        ]
        for t in defaults:
            self.register(t)

    def save_to_file(self, path: str):
        """템플릿을 파일로 저장."""
        from dataclasses import asdict
        data = [asdict(t) for t in self._templates.values()]
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def load_from_file(self, path: str):
        """파일에서 템플릿 로드."""
        data = json.loads(Path(path).read_text())
        for item in data:
            self.register(PromptTemplate(**item))
