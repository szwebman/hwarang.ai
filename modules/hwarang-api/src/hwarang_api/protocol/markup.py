"""HP Output Markup 파서.

LLM 응답의 `message.content` 안에 들어있는 화랑 전용 마크업 섹션을
구조화된 dict 로 추출한다.

지원 섹션:
- @@plan ... @@end       — 작업 계획 (1. 제목 [status] 형식)
- @@diff <path> ... @@end — 파일 변경 미리보기 (+/- 라인)
- @@suggestion: <level> ... @@end — 제안 (info/medium-risk/high-risk)
- @@warning ... @@end    — 주의
- @@error ... @@end      — 오류
- @@summary ... @@end    — 요약
- @@tool: <name> ... @@end — 도구 호출 (메타데이터만 추출)
- @@result ... @@end     — 도구 실행 결과

규칙 (docs/hp-protocol.md §3):
- 섹션 시작: `@@<name>` 또는 `@@<name>: <arg>` (한 줄)
- 섹션 종료: `@@end` (한 줄)
- 본문은 그 사이의 모든 텍스트 (markdown 가능)
"""

from __future__ import annotations

import re
from typing import Any

# 섹션 패턴: `@@<name>` 또는 `@@<name>: <arg>` ~ `@@end`
# - 다중 라인 매칭 (DOTALL)
# - non-greedy (.*?) 로 가장 가까운 @@end 매칭
SECTION_PATTERN = re.compile(
    r"@@(?P<name>[\w-]+)(?:[:\s]+(?P<arg>[^\n]*))?\n(?P<body>.*?)\n@@end",
    re.DOTALL,
)

# plan 라인 패턴: "1. 제목  [status]" — status 선택
_PLAN_LINE = re.compile(r"^\s*(\d+)\.\s*(.+?)(?:\s*\[(\w+)\])?\s*$")


def _parse_plan_body(body: str) -> list[dict[str, str]]:
    """plan 본문에서 번호 매겨진 라인을 파싱."""
    items: list[dict[str, str]] = []
    for line in body.split("\n"):
        m = _PLAN_LINE.match(line)
        if not m:
            continue
        items.append(
            {
                "id": m.group(1),
                "title": m.group(2).strip(),
                "status": (m.group(3) or "pending").lower(),
            }
        )
    return items


def _count_diff_lines(body: str) -> tuple[int, int]:
    """diff 본문에서 추가/삭제 라인 카운트.

    `+++ ` / `--- ` 같은 헤더는 제외 (3글자 이상 prefix 는 헤더로 간주).
    """
    added = 0
    removed = 0
    for line in body.split("\n"):
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def parse_markup(content: str) -> dict[str, Any]:
    """LLM 응답 텍스트에서 HP Markup 섹션을 추출.

    빈 입력 또는 마크업이 없는 일반 텍스트면 모든 섹션이 빈 리스트인 dict 반환.
    """
    result: dict[str, Any] = {
        "plan": [],
        "diffs": [],
        "suggestions": [],
        "warnings": [],
        "errors": [],
        "summary": None,
        "tools": [],
        "results": [],
    }

    if not content:
        return result

    for match in SECTION_PATTERN.finditer(content):
        name = match.group("name").lower()
        arg = (match.group("arg") or "").strip()
        body = match.group("body").strip()

        if name == "plan":
            result["plan"].extend(_parse_plan_body(body))

        elif name == "diff":
            added, removed = _count_diff_lines(body)
            result["diffs"].append(
                {
                    "path": arg or "(unknown)",
                    "added": added,
                    "removed": removed,
                    "raw": body,
                }
            )

        elif name == "suggestion":
            # arg 예: "medium-risk" 또는 "info"
            level = arg.split("-")[0] if arg else "info"
            result["suggestions"].append({"level": level, "text": body, "raw_label": arg})

        elif name == "warning":
            result["warnings"].append({"text": body})

        elif name == "error":
            result["errors"].append({"text": body})

        elif name == "summary":
            # 여러 summary 가 있으면 마지막 것 우선
            result["summary"] = body

        elif name == "tool":
            result["tools"].append({"name": arg, "args_raw": body})

        elif name == "result":
            result["results"].append({"text": body})

    return result


def has_markup(content: str) -> bool:
    """응답에 HP 마크업 섹션이 하나라도 있는지 빠르게 확인."""
    if not content:
        return False
    return bool(SECTION_PATTERN.search(content))


def detect_identity(content: str) -> tuple[str, float]:
    """응답 텍스트에서 화랑 정체성 누출/유지를 추정.

    Returns:
        (identity, confidence) — identity 는 'hwarang' / 'qwen' / 'unknown'
    """
    if not content:
        return "unknown", 0.0

    lower = content.lower()

    qwen_signals = ["qwen", "alibaba cloud", "tongyi", "통이"]
    chatgpt_signals = ["openai", "chatgpt", "gpt-4"]
    hwarang_signals = ["화랑", "hwarang", "퍼시스모어", "persismore"]

    qwen_hit = any(s in lower for s in qwen_signals)
    chatgpt_hit = any(s in lower for s in chatgpt_signals)
    hwarang_hit = any(s in lower for s in hwarang_signals) or "화랑" in content

    if qwen_hit and not hwarang_hit:
        return "qwen", 0.9
    if chatgpt_hit and not hwarang_hit:
        return "chatgpt", 0.9
    if hwarang_hit:
        return "hwarang", 0.95
    # 정체성 언급 없음 — strict 모드 충족 (자기소개 안 했음)
    return "hwarang", 0.6
