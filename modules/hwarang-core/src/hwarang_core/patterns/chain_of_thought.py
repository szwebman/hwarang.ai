"""Chain-of-Thought (CoT) - 단계별 추론.

복잡한 문제를 단계별로 풀도록 유도합니다.
"생각하는 과정"을 명시적으로 출력하게 함으로써 추론 정확도를 높입니다.

기법:
1. Zero-shot CoT: "단계별로 생각해보세요" 추가
2. Few-shot CoT: 예시와 함께 추론 과정 보여주기
3. Self-consistency: 여러 번 추론 후 다수결
4. Tree-of-Thought: 분기별 탐색
"""

from __future__ import annotations

import json
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class CoTStrategy(str, Enum):
    ZERO_SHOT = "zero_shot"        # "단계별로 생각해보세요"
    FEW_SHOT = "few_shot"          # 예시 포함
    SELF_CONSISTENCY = "self_consistency"  # 여러 번 → 다수결
    PLAN_AND_SOLVE = "plan_and_solve"     # 계획 → 실행


# 도메인별 CoT 프롬프트
COT_PROMPTS = {
    "default": "이 문제를 단계별로 생각해보겠습니다.\n\n",

    "code": (
        "이 코딩 문제를 단계별로 해결하겠습니다.\n"
        "1단계: 문제 분석 - 요구사항을 파악합니다\n"
        "2단계: 알고리즘 설계 - 접근 방법을 정합니다\n"
        "3단계: 코드 작성 - 구현합니다\n"
        "4단계: 검증 - 엣지 케이스를 확인합니다\n\n"
    ),

    "legal": (
        "이 법률 문제를 단계별로 분석하겠습니다.\n"
        "1단계: 사실관계 정리 - 핵심 사실을 파악합니다\n"
        "2단계: 관련 법령 확인 - 적용될 법률을 찾습니다\n"
        "3단계: 판례 검토 - 유사 사례를 확인합니다\n"
        "4단계: 법적 판단 - 결론을 도출합니다\n\n"
    ),

    "tax": (
        "이 세무 문제를 단계별로 계산하겠습니다.\n"
        "1단계: 과세 대상 확인 - 과세 요건을 확인합니다\n"
        "2단계: 세율 확인 - 적용될 세율을 찾습니다\n"
        "3단계: 공제/감면 확인 - 적용 가능한 공제를 확인합니다\n"
        "4단계: 세액 계산 - 최종 세액을 산출합니다\n\n"
    ),

    "math": (
        "이 수학 문제를 단계별로 풀겠습니다.\n"
        "풀이:\n"
    ),
}


def apply_cot(
    messages: list[dict],
    strategy: CoTStrategy = CoTStrategy.ZERO_SHOT,
    domain: str = "default",
) -> list[dict]:
    """메시지에 CoT 프롬프트 적용."""
    if strategy == CoTStrategy.ZERO_SHOT:
        cot_prefix = COT_PROMPTS.get(domain, COT_PROMPTS["default"])

        # 마지막 user 메시지에 CoT 유도 추가
        modified = messages.copy()
        for i in range(len(modified) - 1, -1, -1):
            if modified[i]["role"] == "user":
                modified[i] = {
                    "role": "user",
                    "content": modified[i]["content"] + "\n\n" + cot_prefix,
                }
                break
        return modified

    elif strategy == CoTStrategy.PLAN_AND_SOLVE:
        modified = messages.copy()
        for i in range(len(modified) - 1, -1, -1):
            if modified[i]["role"] == "user":
                modified[i] = {
                    "role": "user",
                    "content": (
                        modified[i]["content"] + "\n\n"
                        "먼저 이 문제를 해결하기 위한 계획을 세우세요.\n"
                        "그 다음 계획에 따라 단계별로 실행하세요.\n"
                        "마지막에 최종 답변을 정리하세요."
                    ),
                }
                break
        return modified

    return messages


def extract_final_answer(cot_response: str) -> str:
    """CoT 응답에서 최종 답변 추출."""
    # "따라서", "결론", "최종 답" 등 이후의 텍스트
    markers = ["따라서", "결론:", "최종 답:", "정리하면", "결론적으로", "Answer:", "최종:"]
    for marker in markers:
        idx = cot_response.lower().rfind(marker.lower())
        if idx != -1:
            return cot_response[idx:].strip()
    # 없으면 마지막 문단
    paragraphs = cot_response.strip().split("\n\n")
    return paragraphs[-1] if paragraphs else cot_response
