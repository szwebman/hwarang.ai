"""Hwarang Protocol (HP) v1.0.

OpenAI Chat Completions 와 100% backward 호환되는 화랑 전용 확장 프로토콜.

핵심 컴포넌트:
- types: Pydantic 모델 (HwarangExtension, HwarangResponseExt 등)
- dsl: Prompt DSL → system 메시지 변환
- markup: Output Markup 파서 (@@plan, @@diff, @@suggestion, ...)

스펙 문서: docs/hp-protocol.md
"""

from hwarang_api.protocol.dsl import (
    expand_intent_to_system_prompt,
    estimate_tokens_saved,
    merge_into_messages,
)
from hwarang_api.protocol.markup import parse_markup
from hwarang_api.protocol.types import (
    HPMarkupSection,
    HwarangExtension,
    HwarangResponseExt,
    HwarangWorkflow,
)

__all__ = [
    "HwarangExtension",
    "HwarangResponseExt",
    "HwarangWorkflow",
    "HPMarkupSection",
    "expand_intent_to_system_prompt",
    "merge_into_messages",
    "estimate_tokens_saved",
    "parse_markup",
]
