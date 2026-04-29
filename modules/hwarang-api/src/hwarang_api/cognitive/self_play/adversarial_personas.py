"""6 한국어 특화 토론 페르소나.

각 페르소나는 고유한 system prompt + 초점 영역을 갖는다.
respond_as() 는 페르소나의 관점에서 한 턴의 발언을 생성한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from hwarang_api.knowledge.llm import _chat


@dataclass(frozen=True)
class Persona:
    """토론 페르소나 정의.

    Attributes:
        name: 한글 페르소나 이름 (PERSONAS dict 의 키와 동일).
        system_prompt: LLM 에 주입되는 system message.
        focus: 페르소나가 집중하는 영역 (라우팅/디스플레이용).
    """

    name: str
    system_prompt: str
    focus: str


# ────────────────────────────────────────────────────────────
# 6 페르소나 정의
# ────────────────────────────────────────────────────────────
PERSONAS: dict[str, Persona] = {
    "비판자": Persona(
        name="비판자",
        system_prompt=(
            "당신은 엄격한 비판자다. 답변의 모든 약점을 찾아라. "
            "논리적 비약, 근거 부족, 사실 오류, 누락된 반례를 직설적으로 지적하라. "
            "한국어로 간결하게 답하라. 칭찬은 하지 마라."
        ),
        focus="weakness_detection",
    ),
    "옹호자": Persona(
        name="옹호자",
        system_prompt=(
            "당신은 답변을 옹호한다. 강점과 정당화를 제시하라. "
            "비판에 대해 합리적 반박과 보완 근거를 한국어로 제시하되, "
            "맹목적 옹호는 금지 — 명백한 오류는 인정하라."
        ),
        focus="defense_justification",
    ),
    "회의주의자": Persona(
        name="회의주의자",
        system_prompt=(
            "당신은 모든 출처와 가정을 의심한다. 반례를 제시하라. "
            "'정말 그런가?' 라는 질문을 끝까지 던지고, "
            "암묵적 전제와 인용 없는 주장을 한국어로 폭로하라."
        ),
        focus="source_skepticism",
    ),
    "실용주의자": Persona(
        name="실용주의자",
        system_prompt=(
            "당신은 실제 적용 가능성을 본다. 이론은 좋지만 현실에서 작동하나? "
            "한국 사회/조직/개인 맥락에서 실행 시 비용, 부작용, 장애물을 한국어로 짚어라."
        ),
        focus="real_world_applicability",
    ),
    "법률가": Persona(
        name="법률가",
        system_prompt=(
            "당신은 한국 법규/규제 관점에서 본다. 법적 리스크는? "
            "관련 법령/판례/규정을 한국어로 언급하고, "
            "잠재적 위반 가능성과 책임 소재를 명확히 짚어라."
        ),
        focus="korean_legal_risk",
    ),
    "윤리학자": Persona(
        name="윤리학자",
        system_prompt=(
            "당신은 윤리적 영향을 본다. 누구에게 해가 가는가? "
            "공정성/약자 보호/장기 영향/존엄성 관점에서 한국어로 분석하고, "
            "보이지 않는 피해자나 외부효과를 드러내라."
        ),
        focus="ethical_harm_analysis",
    ),
}


def _format_history(history: list[dict]) -> str:
    """이전 턴 히스토리를 LLM 프롬프트용 문자열로 직렬화."""
    if not history:
        return "(아직 다른 페르소나의 발언 없음)"
    lines: list[str] = []
    for h in history:
        persona = str(h.get("persona", "?"))
        content = str(h.get("content", "")).strip()
        round_n = h.get("round", "?")
        if content:
            lines.append(f"[Round {round_n}] {persona}: {content}")
    return "\n".join(lines) if lines else "(아직 다른 페르소나의 발언 없음)"


async def respond_as(
    persona_name: str,
    question: str,
    current_answer: str,
    history: list[dict],
) -> str:
    """페르소나 관점에서 한 턴 발언 생성.

    Args:
        persona_name: PERSONAS 키 (예: "비판자").
        question: 원 질문.
        current_answer: 토론 대상 초기 답변.
        history: [{round, persona, content, ...}, ...] 형식의 이전 발언.

    Returns:
        한국어 발언 문자열. LLM 실패 시 빈 문자열.
    """
    persona = PERSONAS.get(persona_name)
    if persona is None:
        return ""

    history_str = _format_history(history)
    prompt = (
        f"## 원 질문\n{(question or '').strip()[:1500]}\n\n"
        f"## 토론 대상 초기 답변\n{(current_answer or '').strip()[:2000]}\n\n"
        f"## 지금까지의 토론\n{history_str[:3000]}\n\n"
        f"## 당신의 차례 ({persona.name})\n"
        f"위 답변에 대해 당신의 페르소나에 충실하게 1~3 문장으로 발언하라. "
        f"중복 금지 — 이전 발언과 다른 새로운 관점을 추가하라."
    )

    resp = await _chat(prompt, system=persona.system_prompt, max_tokens=350)
    return (resp or "").strip()


__all__ = ["Persona", "PERSONAS", "respond_as"]
