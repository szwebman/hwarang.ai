"""모듈 7: 안전 필터 에이전트

AI 응답의 유해성/환각/개인정보 자동 필터링.
서빙 시 응답을 검사하고 문제 있으면 차단/수정.
"""

import re, logging

logger = logging.getLogger(__name__)


class SafetyFilterModule:
    def __init__(self, config):
        self.config = config
        self.violations = 0

    # 유해 패턴
    HARMFUL_PATTERNS = [
        r"(?:폭탄|폭발물|무기)\s*(?:만드|제조|제작)",
        r"(?:마약|약물)\s*(?:만드|합성|제조)",
        r"(?:해킹|크래킹)\s*(?:방법|도구|하는\s*법)",
        r"(?:자해|자살)\s*(?:방법|도구)",
    ]

    # 개인정보 패턴
    PII_PATTERNS = [
        r"\d{6}[-\s]?\d{7}",           # 주민등록번호
        r"\d{3}[-\s]?\d{4}[-\s]?\d{4}", # 전화번호
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", # 이메일
        r"\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}", # 카드번호
    ]

    def check_response(self, response: str) -> dict:
        """응답 안전성 검사."""
        issues = []

        if self.config.filter_harmful:
            for pattern in self.HARMFUL_PATTERNS:
                if re.search(pattern, response, re.IGNORECASE):
                    issues.append({"type": "harmful", "pattern": pattern[:30]})

        if self.config.filter_pii:
            for pattern in self.PII_PATTERNS:
                matches = re.findall(pattern, response)
                if matches:
                    issues.append({"type": "pii", "count": len(matches)})

        if self.config.filter_hallucination:
            hall = self._detect_hallucination(response)
            if hall:
                issues.append({"type": "hallucination", "detail": hall})

        is_safe = len(issues) == 0
        if not is_safe:
            self.violations += 1

        return {"safe": is_safe, "issues": issues}

    def sanitize(self, response: str) -> str:
        """문제 부분 제거/마스킹."""
        # PII 마스킹
        for pattern in self.PII_PATTERNS:
            response = re.sub(pattern, "[개인정보 마스킹]", response)
        return response

    def _detect_hallucination(self, response: str) -> str | None:
        """환각 간이 감지."""
        # 존재하지 않는 법 조항 패턴
        fake_law = re.search(r"(민법|형법)\s*제?\s*(\d{4,})조", response)
        if fake_law:
            article = int(fake_law.group(2))
            if article > 1000:
                return f"의심: {fake_law.group(0)} (조항 번호 비정상)"
        return None

    def get_stats(self) -> dict:
        return {"violations_caught": self.violations}
