"""코드 텍스트 → 언어 식별.

휴리스틱:
  - ``def`` / ``import`` / ``print()``                 → Python
  - ``const`` / ``require()`` / ``console.log``        → JavaScript
  - ``interface`` / ``type X =`` / ``: string``        → TypeScript
  - ``fn`` / ``impl`` / ``println!``                   → Rust
  - ``package`` / ``func`` / ``fmt.Print``             → Go

우선순위: hint > 패턴 매칭 > 기본 (python).
TypeScript ↔ JavaScript 충돌 시 TS 패턴이 1개라도 있으면 TS 로 분류.
"""

from __future__ import annotations

import re

PATTERNS = {
    "python": [
        r"^\s*def\s+\w+\(",
        r"^\s*import\s+\w+",
        r"^\s*from\s+\w+\s+import",
        r"^\s*class\s+\w+:",
        r"print\(",
    ],
    "typescript": [
        r"^\s*interface\s+\w+",
        r"^\s*type\s+\w+\s*=",
        r":\s*string\b|:\s*number\b|:\s*boolean\b",
        r"^\s*import\s+.*from\s+['\"]",  # 모듈 import
        r"^\s*export\s+(default\s+)?(class|function|interface|type|const)",
    ],
    "javascript": [
        r"^\s*const\s+\w+\s*=",
        r"^\s*let\s+\w+\s*=",
        r"^\s*function\s+\w+\(",
        r"^\s*require\(['\"]",
        r"console\.log\(",
    ],
    "rust": [
        r"^\s*fn\s+\w+\(",
        r"^\s*impl\s+",
        r"^\s*use\s+\w+::",
        r"println!",
    ],
    "go": [
        r"^\s*package\s+\w+",
        r"^\s*func\s+\w+\(",
        r"^\s*import\s*\(",
        r"fmt\.Print",
    ],
}

_HINT_NORMALIZE = {
    "py": "python",
    "python": "python",
    "js": "javascript",
    "node": "javascript",
    "javascript": "javascript",
    "ts": "typescript",
    "typescript": "typescript",
    "rs": "rust",
    "rust": "rust",
    "go": "go",
    "golang": "go",
}


def detect_language(code: str, hint: str | None = None) -> str:
    """우선순위: hint > 패턴 매칭 > 기본 (python)."""
    if hint:
        normalized = _HINT_NORMALIZE.get(hint.lower())
        if normalized:
            return normalized

    scores: dict[str, int] = {lang: 0 for lang in PATTERNS}
    for lang, patterns in PATTERNS.items():
        for p in patterns:
            scores[lang] += len(re.findall(p, code, re.MULTILINE))

    # TypeScript vs JavaScript: TS 키워드가 있으면 TS 우선
    if scores["typescript"] > 0 and scores["typescript"] >= scores["javascript"] - 1:
        # TS 가 JS 보다 1점 이상 뒤지지 않으면 TS 로 본다
        # 단, 다른 언어가 더 높을 수 있으므로 전체 비교 필요
        ts_dominant = scores["typescript"]
        # JS 점수를 TS 로 흡수해 다른 언어와 비교
        js_score = scores["javascript"]
        scores_compare = dict(scores)
        scores_compare["typescript"] = max(ts_dominant, js_score)
        scores_compare["javascript"] = 0
        best = max(scores_compare, key=scores_compare.get)
        return best if scores_compare[best] > 0 else "python"

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "python"


__all__ = ["PATTERNS", "detect_language"]
