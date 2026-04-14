"""Safety / Guardrails - 안전 필터 시스템.

모든 입력/출력을 검사하여 유해 콘텐츠를 차단합니다.

차단 대상:
1. 유해 콘텐츠 (폭력, 범죄, 혐오)
2. 개인정보 생성 (가짜 주민번호 등)
3. 프롬프트 인젝션 공격
4. 시스템 프롬프트 유출 시도
5. 잘못된 전문 조언 (법률/세무 면책)
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SafetyLevel(str, Enum):
    SAFE = "safe"
    WARNING = "warning"
    BLOCKED = "blocked"


@dataclass
class SafetyCheckResult:
    level: SafetyLevel
    category: str
    reason: str
    modified_text: str | None = None  # 수정된 텍스트 (WARNING일 때)


# 유해 키워드 패턴
HARMFUL_PATTERNS = [
    (r"폭탄.*(만들|제조|제작)", "violence", "폭발물 제조 관련"),
    (r"(마약|메스암페타민|필로폰).*(만들|제조|합성)", "drugs", "마약 제조 관련"),
    (r"자살.*(방법|하는\s*법)", "self_harm", "자해 관련"),
    (r"해킹.*(방법|하는\s*법|툴)", "hacking", "불법 해킹 관련"),
]

# 프롬프트 인젝션 패턴
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"system\s*prompt|시스템\s*프롬프트",
    r"you\s+are\s+now\s+",
    r"새로운\s*역할|역할을\s*바꿔",
    r"DAN\s*mode|jailbreak",
    r"위의\s*지시.*무시",
    r"원래\s*지시.*잊어",
]

# 개인정보 패턴 (생성 방지)
PII_OUTPUT_PATTERNS = [
    (r"\d{6}-[1-4]\d{6}", "주민등록번호"),
    (r"\d{3}-\d{2}-\d{5}", "사업자등록번호"),
    (r"\d{4}-?\d{4}-?\d{4}-?\d{4}", "신용카드번호"),
]

# 전문 분야 면책 조항
DISCLAIMER_DOMAINS = {
    "legal": "이 답변은 법률 정보 제공 목적이며, 구체적인 법률 자문은 반드시 변호사와 상담하세요.",
    "tax": "이 답변은 세무 정보 제공 목적이며, 실제 세금 신고는 세무사와 상담하세요.",
    "medical": "이 답변은 의료 정보 제공 목적이며, 진단과 치료는 반드시 의사와 상담하세요.",
}


class SafetyGuard:
    """입력/출력 안전 필터."""

    def __init__(self, strict: bool = True):
        self.strict = strict

    def check_input(self, text: str) -> SafetyCheckResult:
        """입력 텍스트 안전 검사."""
        # 1. 프롬프트 인젝션 검사
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return SafetyCheckResult(
                    level=SafetyLevel.BLOCKED,
                    category="prompt_injection",
                    reason="프롬프트 인젝션이 감지되었습니다",
                )

        # 2. 유해 콘텐츠 검사
        for pattern, category, reason in HARMFUL_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return SafetyCheckResult(
                    level=SafetyLevel.BLOCKED,
                    category=category,
                    reason=reason,
                )

        return SafetyCheckResult(level=SafetyLevel.SAFE, category="ok", reason="")

    def check_output(self, text: str, domain: str | None = None) -> SafetyCheckResult:
        """출력 텍스트 안전 검사."""
        modified = text

        # 1. 개인정보 마스킹
        for pattern, pii_type in PII_OUTPUT_PATTERNS:
            if re.search(pattern, modified):
                modified = re.sub(pattern, f"[{pii_type} 마스킹됨]", modified)
                logger.warning(f"출력에서 {pii_type} 감지 → 마스킹")

        # 2. 도메인 면책 조항 추가
        if domain and domain in DISCLAIMER_DOMAINS:
            disclaimer = DISCLAIMER_DOMAINS[domain]
            if disclaimer not in modified:
                modified += f"\n\n> ⚠️ {disclaimer}"

        if modified != text:
            return SafetyCheckResult(
                level=SafetyLevel.WARNING,
                category="modified",
                reason="출력이 수정되었습니다",
                modified_text=modified,
            )

        return SafetyCheckResult(level=SafetyLevel.SAFE, category="ok", reason="")

    def get_safe_response(self, category: str) -> str:
        """차단 시 안전한 대체 응답."""
        responses = {
            "prompt_injection": "요청을 처리할 수 없습니다.",
            "violence": "폭력적인 내용에 대해서는 답변할 수 없습니다.",
            "drugs": "불법적인 내용에 대해서는 답변할 수 없습니다.",
            "self_harm": "도움이 필요하시면 자살예방상담전화 1393으로 연락해주세요.",
            "hacking": "불법적인 활동에 대해서는 답변할 수 없습니다.",
        }
        return responses.get(category, "요청을 처리할 수 없습니다.")
