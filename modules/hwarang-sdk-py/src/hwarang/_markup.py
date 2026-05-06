"""HP Output Markup 파서 (TS ``markup.ts`` / 서버 ``markup.py`` 와 동일 로직).

지원 섹션:
- ``@@plan``                — 번호 매겨진 항목 ``"1. 제목 [status]"``
- ``@@diff <path>``         — unified diff (+/- 라인 카운트)
- ``@@suggestion: <level>`` — 제안 (info / medium-risk / high-risk ...)
- ``@@warning``             — 경고
- ``@@error``               — 오류
- ``@@summary``             — 한 줄 요약
- ``@@tool: <name>``        — 도구 호출 메타
- ``@@result``              — 도구 실행 결과

규칙 (``docs/hp-protocol.md`` §3):
- 시작: ``@@<name>`` 또는 ``@@<name>: <arg>`` (한 줄)
- 종료: ``@@end`` (한 줄)
- 본문은 그 사이의 모든 텍스트 (markdown 가능)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# ``@@<name>`` 또는 ``@@<name>: <arg>`` ~ ``@@end`` 매칭 (non-greedy, 다중라인)
_SECTION_RE = re.compile(
    r"@@(?P<name>[\w-]+)(?:[:\s]+(?P<arg>[^\n]*))?\n(?P<body>.*?)\n@@end",
    re.DOTALL,
)

# ``"1. 제목  [status]"`` — status 는 선택
_PLAN_LINE_RE = re.compile(r"^\s*(\d+)\.\s*(.+?)(?:\s*\[(\w+)\])?\s*$")


def _parse_plan_body(body: str) -> List[Dict[str, str]]:
    """plan 본문에서 번호 매겨진 라인을 추출."""
    items: List[Dict[str, str]] = []
    for line in body.split("\n"):
        m = _PLAN_LINE_RE.match(line)
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


def _count_diff_lines(body: str) -> Tuple[int, int]:
    """diff 본문에서 추가/삭제 라인 카운트.

    ``+++`` / ``---`` 헤더 라인은 제외.
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


def parse_markup(content: str) -> Dict[str, Any]:
    """LLM 응답 텍스트에서 HP Markup 섹션을 추출.

    빈 입력 또는 마크업이 없는 일반 텍스트면 모든 섹션이 빈 리스트인 dict 반환.

    Returns:
        ``MarkupSection(**result)`` 로 바로 dataclass 변환 가능한 dict.
    """
    result: Dict[str, Any] = {
        "plan": [],
        "diffs": [],
        "suggestions": [],
        "warnings": [],
        "errors": [],
        "tools": [],
        "results": [],
        "summary": None,
    }

    if not content:
        return result

    for match in _SECTION_RE.finditer(content):
        name = (match.group("name") or "").lower()
        arg = (match.group("arg") or "").strip()
        body = (match.group("body") or "").strip()

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
            level = arg.split("-")[0] if arg else "info"
            result["suggestions"].append(
                {"level": level or "info", "text": body, "raw_label": arg}
            )

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

        # 알 수 없는 섹션은 무시 (forward-compat)

    return result


def has_markup(content: str) -> bool:
    """응답에 HP 마크업 섹션이 하나라도 있는지 빠르게 확인."""
    if not content:
        return False
    return bool(_SECTION_RE.search(content))
