"""HP (Hwarang Protocol) v1.0 — Python 타입 정의.

``docs/hp-protocol.md`` 와 미러링된다. Pydantic 의존성을 피하기 위해
``dataclass`` + ``TypedDict`` 만 사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, TypedDict

# ─────────────────────────────────────────────────────────
# OpenAI 호환 타입
# ─────────────────────────────────────────────────────────

Role = Literal["system", "user", "assistant", "tool"]


class ChatMessage(TypedDict, total=False):
    """OpenAI Chat Completions 메시지."""

    role: Role
    content: Optional[str]
    tool_calls: List[Dict[str, Any]]
    tool_call_id: str
    name: str


class ToolFunction(TypedDict):
    name: str
    arguments: str


class ToolCall(TypedDict):
    id: str
    type: Literal["function"]
    function: ToolFunction


class ToolDefinitionFunction(TypedDict, total=False):
    name: str
    description: str
    parameters: Dict[str, Any]


class ToolDefinition(TypedDict):
    type: Literal["function"]
    function: ToolDefinitionFunction


# ─────────────────────────────────────────────────────────
# HP 확장 타입
# ─────────────────────────────────────────────────────────

Intent = Literal[
    "refactor",
    "explain",
    "fix",
    "add",
    "test",
    "review",
    "optimize",
    "secure",
    "document",
    "translate",
    "diagnose",
    "commit",
    "plan",
]
Scope = Literal["line", "selection", "file", "module", "project"]
Language = Literal["ko", "en", "mixed"]
Format = Literal["plain", "markup", "json"]
Identity = Literal["strict", "lenient"]
Safety = Literal["loose", "standard", "strict"]
Expertise = Literal["junior", "mid", "senior"]
Style = Literal["functional", "oop", "declarative", "imperative"]
OnFail = Literal["abort", "retry-once", "continue", "rollback"]


class WorkflowStep(TypedDict, total=False):
    id: str
    tool: str
    command: str
    depends: List[str]


class Workflow(TypedDict, total=False):
    name: str
    steps: List[WorkflowStep]
    on_fail: OnFail
    max_iterations: int


class WorkspaceHint(TypedDict, total=False):
    root: str
    stack: List[str]
    branch: str


class HwarangExtension(TypedDict, total=False):
    """``@hwarang`` 요청 확장 — 모든 필드 선택."""

    # Prompt DSL
    intent: Intent
    scope: Scope
    target: str
    language: Language
    constraints: List[str]
    style: str
    expertise: Expertise

    # Output Markup
    format: Format
    include: List[str]

    # Workflow
    workflow: Workflow

    # Identity / Safety
    identity: Identity
    safety: Safety
    redact_secrets: bool

    # Context Hints
    workspace: WorkspaceHint

    # Telemetry
    telemetry: List[str]


# ─────────────────────────────────────────────────────────
# Markup 파싱 결과
# ─────────────────────────────────────────────────────────


class MarkupPlanItem(TypedDict):
    id: str
    title: str
    status: str


class MarkupDiff(TypedDict, total=False):
    path: str
    added: int
    removed: int
    raw: str


class MarkupSuggestion(TypedDict, total=False):
    level: str
    text: str
    raw_label: str


class MarkupNote(TypedDict):
    text: str


class MarkupTool(TypedDict, total=False):
    name: str
    args_raw: str


class MarkupResult(TypedDict):
    text: str


@dataclass
class MarkupSection:
    """파싱된 HP 마크업 섹션 모음."""

    plan: List[MarkupPlanItem] = field(default_factory=list)
    diffs: List[MarkupDiff] = field(default_factory=list)
    suggestions: List[MarkupSuggestion] = field(default_factory=list)
    warnings: List[MarkupNote] = field(default_factory=list)
    errors: List[MarkupNote] = field(default_factory=list)
    tools: List[MarkupTool] = field(default_factory=list)
    results: List[MarkupResult] = field(default_factory=list)
    summary: Optional[str] = None

    def is_empty(self) -> bool:
        """마크업이 하나도 없으면 True."""
        return (
            not self.plan
            and not self.diffs
            and not self.suggestions
            and not self.warnings
            and not self.errors
            and not self.tools
            and not self.results
            and self.summary is None
        )


# ─────────────────────────────────────────────────────────
# 응답 메타데이터
# ─────────────────────────────────────────────────────────


class ToolCallMeta(TypedDict, total=False):
    id: str
    risk: Literal["low", "medium", "high"]
    auto_approved: bool
    needs_user: bool


class WorkflowProgress(TypedDict, total=False):
    name: str
    current_step: str
    completed: List[str]
    remaining: List[str]


class HwarangResponseMeta(TypedDict, total=False):
    format_used: Format
    lora_used: str
    identity: str
    identity_confidence: float
    markup: Dict[str, Any]
    tool_calls_meta: List[ToolCallMeta]
    workflow: WorkflowProgress
    telemetry: Dict[str, Any]


# ─────────────────────────────────────────────────────────
# 응답 wrapper
# ─────────────────────────────────────────────────────────


@dataclass
class ChatResponse:
    """``/v1/chat/completions`` 응답을 감싼 편의 객체.

    원본 dict (``raw``) 와 마크업 파싱 결과 (``markup``) 를 함께 보관한다.
    OpenAI SDK 와 비슷하게 ``response.text`` / ``response.tool_calls``
    같은 단축 접근자를 제공한다.
    """

    raw: Dict[str, Any]
    text: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    markup: Optional[MarkupSection] = None

    @property
    def hwarang(self) -> Dict[str, Any]:
        """``@hwarang`` 응답 메타데이터 (서버가 채워준 경우)."""
        return self.raw.get("@hwarang") or self.raw.get("hwarang") or {}

    @property
    def usage(self) -> Dict[str, Any]:
        return self.raw.get("usage") or {}

    @property
    def model(self) -> str:
        return self.raw.get("model") or ""

    @property
    def id(self) -> str:
        return self.raw.get("id") or ""

    @property
    def finish_reason(self) -> str:
        choices = self.raw.get("choices") or []
        if not choices:
            return "stop"
        return choices[0].get("finish_reason") or "stop"

    @property
    def message(self) -> Dict[str, Any]:
        choices = self.raw.get("choices") or []
        if not choices:
            return {}
        return choices[0].get("message") or {}


# ─────────────────────────────────────────────────────────
# /v1/hwarang/do 단순 엔트리
# ─────────────────────────────────────────────────────────


class DoRequest(TypedDict, total=False):
    intent: Intent
    scope: Scope
    target: str
    language: Language
    input: str
    constraints: List[str]
    workflow: Any  # List[str] | Workflow


class DoResponse(TypedDict, total=False):
    ok: bool
    summary: str
    files_changed: List[str]
    next_steps: List[str]
