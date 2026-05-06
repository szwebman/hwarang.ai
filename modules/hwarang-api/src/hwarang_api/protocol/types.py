"""Hwarang Protocol (HP) Pydantic 모델.

HP-Request 의 `@hwarang` 확장 필드 + HP-Response 의 `@hwarang` 응답 필드 정의.

모든 필드는 선택 사항 — `@hwarang` 자체가 없거나 일부 필드만 있어도 검증 통과.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# 표준 의도 목록 (docs/hp-protocol.md §5)
IntentLiteral = Literal[
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

ScopeLiteral = Literal["line", "selection", "file", "module", "project"]

LanguageLiteral = Literal["ko", "en", "mixed"]

ExpertiseLiteral = Literal["junior", "mid", "senior"]

FormatLiteral = Literal["plain", "markup", "json"]

OnFailLiteral = Literal["abort", "retry-once", "continue", "rollback"]

IdentityLiteral = Literal["strict", "lenient"]

SafetyLiteral = Literal["loose", "standard", "strict"]


class HwarangWorkflow(BaseModel):
    """다단계 워크플로우 정의.

    `name` 만 주면 사전 정의 카탈로그 (deploy-mobile/add-api/bug-fix/...) 사용.
    `steps` 를 주면 ad-hoc 단계 실행.
    """

    model_config = ConfigDict(extra="allow")

    name: Optional[str] = None
    steps: Optional[list[dict]] = None
    on_fail: OnFailLiteral = "abort"
    max_iterations: int = Field(default=12, ge=1, le=64)


class HwarangExtension(BaseModel):
    """HP-Request 의 `@hwarang` 확장 필드.

    OpenAI 표준 ChatCompletionRequest 와 별도로 전송됨.
    모든 필드는 선택 — 비어 있어도 검증 통과 (= 화랑 SDK 미사용 클라이언트 호환).
    """

    model_config = ConfigDict(extra="allow")

    # ── Prompt DSL (입력 효율) ──
    intent: Optional[IntentLiteral] = None
    scope: Optional[ScopeLiteral] = None
    target: Optional[str] = None
    language: LanguageLiteral = "ko"
    constraints: list[str] = Field(default_factory=list)
    style: Optional[str] = None
    expertise: Optional[ExpertiseLiteral] = None

    # ── Output Markup (출력 구조화) ──
    format: FormatLiteral = "plain"
    include: list[str] = Field(default_factory=list)

    # ── Workflow (다단계 자동화) ──
    workflow: Optional[HwarangWorkflow] = None

    # ── Identity / Safety ──
    identity: IdentityLiteral = "strict"
    safety: SafetyLiteral = "standard"
    redact_secrets: bool = True

    # ── Context Hints ──
    workspace: Optional[dict] = None

    # ── Telemetry Opt-in ──
    telemetry: list[str] = Field(default_factory=list)


class HPMarkupSection(BaseModel):
    """HP Output Markup 파싱 결과.

    LLM 응답의 `@@plan / @@diff / @@suggestion / @@warning / @@error / @@summary` 섹션을
    구조화된 형태로 표현.
    """

    plan: list[dict] = Field(default_factory=list)
    diffs: list[dict] = Field(default_factory=list)
    suggestions: list[dict] = Field(default_factory=list)
    warnings: list[dict] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
    summary: Optional[str] = None


class HwarangResponseExt(BaseModel):
    """HP-Response 의 `@hwarang` 응답 확장.

    OpenAI 호환 응답 본문 옆에 별도 필드로 전달.
    """

    model_config = ConfigDict(extra="allow")

    format_used: Optional[str] = None
    lora_used: Optional[str] = None
    identity: Optional[str] = None
    identity_confidence: Optional[float] = None
    markup: Optional[HPMarkupSection] = None
    tool_calls_meta: list[dict] = Field(default_factory=list)
    workflow: Optional[dict] = None
    telemetry: dict = Field(default_factory=dict)
