"""HP Prompt DSL → 메시지 변환.

`@hwarang.intent / scope / target / ...` 같은 DSL 필드를 LLM 이 이해할 수 있는
한국어 system prompt 로 확장하고, 기존 messages 배열에 병합한다.

토큰 절약 효과:
- 사용자가 매번 "한국어로 답해" "리팩토링 해줘" 등을 풀어 쓰지 않아도 됨
- 정형화된 보강 → 캐싱 친화적
"""

from __future__ import annotations

from hwarang_api.protocol.types import HwarangExtension


# 의도 → 한국어 시스템 지시 매핑 (docs/hp-protocol.md §5)
_INTENT_DESCRIPTIONS: dict[str, str] = {
    "refactor": "기존 코드를 개선합니다. 동작은 같게 유지하고 가독성/구조를 향상시키세요.",
    "explain": "코드를 한국어로 명확히 설명합니다. 핵심 흐름을 먼저, 세부는 그 다음.",
    "fix": "버그를 진단하고 수정합니다. 증상이 아니라 근본 원인을 찾으세요.",
    "add": "새 기능을 추가합니다. 기존 코드 스타일과 일관되게 작성하세요.",
    "test": "테스트를 작성하거나 실행합니다. 엣지 케이스 우선.",
    "review": "코드 리뷰를 수행합니다 — 가독성, 성능, 보안, 타입 안전성 관점에서.",
    "optimize": "성능을 최적화합니다. 측정 → 병목 식별 → 개선 순서로.",
    "secure": "보안 취약점을 점검합니다 (XSS / SQLi / Path Traversal / SSRF / 인증 우회 등).",
    "document": "문서/주석을 추가합니다. 한국어로, 왜(why) 위주로.",
    "translate": "다른 언어로 변환합니다 (예: JS → TS, Python → Rust).",
    "diagnose": "에러/문제의 근본 원인을 진단합니다. 가설 → 검증.",
    "commit": "변경사항을 git 으로 커밋합니다. Conventional Commits 형식 권장.",
    "plan": "작업 계획만 작성합니다 (실제 코드 변경 X). 단계별로 정리.",
}

_SCOPE_DESCRIPTIONS: dict[str, str] = {
    "line": "한 줄만",
    "selection": "선택한 부분만",
    "file": "단일 파일 범위",
    "module": "모듈/디렉토리 범위",
    "project": "프로젝트 전체",
}


def expand_intent_to_system_prompt(ext: HwarangExtension) -> str:
    """`@hwarang` 확장을 system 메시지에 prepend 할 텍스트로 변환.

    빈 확장 (모든 필드 None/default) 이면 빈 문자열 반환.
    """
    parts: list[str] = []

    # ── 작업 의도 ──
    if ext.intent:
        desc = _INTENT_DESCRIPTIONS.get(ext.intent, ext.intent)
        parts.append(f"[작업 의도] {desc}")

    # ── 작업 범위 ──
    if ext.scope:
        scope_desc = _SCOPE_DESCRIPTIONS.get(ext.scope, ext.scope)
        parts.append(f"[작업 범위] {scope_desc}")

    # ── 대상 ──
    if ext.target:
        parts.append(f"[대상] {ext.target}")

    # ── 언어 ──
    if ext.language == "ko":
        parts.append("[언어] 한국어로 답변합니다. 코드 주석은 한국어, 변수명/식별자는 영어.")
    elif ext.language == "en":
        parts.append("[Language] Reply in English. Code comments in English.")
    elif ext.language == "mixed":
        parts.append("[언어] 설명은 한국어, 기술 용어는 영어 그대로 (혼용 허용).")

    # ── 제약 ──
    if ext.constraints:
        joined = "\n".join(f"- {c}" for c in ext.constraints)
        parts.append(f"[제약]\n{joined}")

    # ── 코딩 스타일 ──
    if ext.style:
        parts.append(f"[코딩 스타일] {ext.style}")

    # ── 답변 깊이 ──
    if ext.expertise == "senior":
        parts.append(
            "[답변 깊이] 시니어 수준 — 트레이드오프, 함정, 엣지 케이스를 모두 다루세요."
        )
    elif ext.expertise == "junior":
        parts.append(
            "[답변 깊이] 주니어 수준 — 단계별 설명, 기본 개념부터 차근차근."
        )
    elif ext.expertise == "mid":
        parts.append("[답변 깊이] 중급 수준 — 핵심 위주, 기본은 생략.")

    # ── 정체성 ──
    if ext.identity == "strict":
        parts.append(
            "[정체성] 당신은 화랑(Hwarang) AI 입니다. 퍼시스모어가 만든 한국형 코딩 어시스턴트입니다. "
            "'Qwen', 'Alibaba Cloud', 'ChatGPT', 'OpenAI' 등 다른 AI 라고 자기 소개하지 마세요."
        )

    # ── 안전 ──
    if ext.safety == "strict":
        parts.append(
            "[안전 모드] 위험한 명령 (rm -rf /, DROP TABLE, sudo 등) 은 거부하세요. "
            "의료/법률/투자 조언에는 disclaimer 를 붙이세요."
        )
    elif ext.safety == "loose":
        parts.append("[안전 모드] 느슨 — 기술 질문에 적극 답변, 위험 명령도 사용자 책임 하에 안내.")

    # ── 출력 형식 ──
    if ext.format == "markup":
        parts.append(
            "[출력 형식] HP Markup 사용:\n"
            "@@plan ... @@end (작업 계획, '1. 제목 [status]' 형식)\n"
            "@@diff <path> ... @@end (파일 변경 미리보기, +/- 라인)\n"
            "@@suggestion: <level> ... @@end (info/medium-risk/high-risk)\n"
            "@@warning ... @@end (주의 사항)\n"
            "@@error ... @@end (오류)\n"
            "@@summary ... @@end (마무리 요약)"
        )
    elif ext.format == "json":
        parts.append("[출력 형식] JSON 객체로만 응답하세요. 다른 텍스트 금지.")

    # ── include 섹션 힌트 ──
    if ext.include:
        joined = ", ".join(ext.include)
        parts.append(f"[필수 섹션] 응답에 다음을 반드시 포함: {joined}")

    # ── 워크스페이스 컨텍스트 ──
    if ext.workspace:
        ws = ext.workspace
        if ws.get("stack"):
            parts.append(f"[기술 스택] {', '.join(ws['stack'])}")
        if ws.get("root"):
            parts.append(f"[작업 루트] {ws['root']}")
        if ws.get("branch"):
            parts.append(f"[현재 브랜치] {ws['branch']}")

    # ── 워크플로우 ──
    if ext.workflow:
        wf = ext.workflow
        if wf.name:
            parts.append(f"[워크플로우] {wf.name} (실패 시: {wf.on_fail})")
        elif wf.steps:
            step_names = [str(s.get("id") or s.get("name") or "?") for s in wf.steps]
            parts.append(f"[워크플로우 단계] {' → '.join(step_names)}")

    return "\n\n".join(parts)


def merge_into_messages(messages: list[dict], ext: HwarangExtension) -> list[dict]:
    """HP DSL 보강을 messages 의 첫 system 메시지에 prepend.

    - system 메시지가 있으면 그 content 앞에 붙임
    - 없으면 새 system 메시지를 맨 앞에 삽입
    - 보강할 내용이 없으면 messages 그대로 반환

    원본 messages 는 변경하지 않음 (얕은 복사 후 반환).
    """
    boost = expand_intent_to_system_prompt(ext)
    if not boost:
        return list(messages)

    new_messages = list(messages)
    sys_idx = next(
        (i for i, m in enumerate(new_messages) if m.get("role") == "system"),
        -1,
    )

    if sys_idx >= 0:
        original = new_messages[sys_idx]
        new_messages[sys_idx] = {
            **original,
            "content": boost + "\n\n" + (original.get("content") or ""),
        }
    else:
        new_messages.insert(0, {"role": "system", "content": boost})

    return new_messages


def estimate_tokens_saved(ext: HwarangExtension) -> int:
    """DSL 사용으로 절약된 토큰을 대략 추정.

    실제 토크나이저 없이 휴리스틱 — 텔레메트리용 근사값.
    한 영어/한국어 단어 ≈ 1.3 토큰 가정.
    """
    saved = 0

    # intent: 보통 사용자가 "리팩토링 해주세요. 동작은 같게..." 풀어 쓰는 분량
    if ext.intent:
        saved += 25
    if ext.scope:
        saved += 8
    if ext.target:
        saved += 10
    if ext.language and ext.language != "mixed":
        saved += 12
    saved += len(ext.constraints) * 6
    if ext.style:
        saved += 5
    if ext.expertise:
        saved += 10
    if ext.identity == "strict":
        saved += 30
    if ext.safety == "strict":
        saved += 20
    if ext.format == "markup":
        saved += 35
    if ext.workspace:
        if ext.workspace.get("stack"):
            saved += len(ext.workspace["stack"]) * 3
        if ext.workspace.get("root"):
            saved += 8

    return saved
