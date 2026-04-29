"""다단계 안전 게이트.

각 검사가 fail-fast 로 동작하되, 모든 위험 요소를 한 번에 보고하기 위해
앞쪽 critical/sandbox 거부 외에는 누적 검사를 한다.

approved_for_pr=True 의 의미:
    "Draft PR 로 제안해도 좋다" — 자동 머지 허가가 절대 아니다.
    최종 머지는 반드시 사람이 한다.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List

from .change_proposal import ChangeProposal
from .sandbox_test import SandboxResult

logger = logging.getLogger(__name__)


# 위험 패턴 — proposed_code 에 절대 등장해서는 안 됨.
DANGEROUS_PATTERNS: tuple[tuple[str, str], ...] = (
    ("exec_call", r"\bexec\s*\("),
    ("eval_call", r"\beval\s*\("),
    ("dunder_import", r"__import__\s*\("),
    ("os_system", r"\bos\.system\s*\("),
    ("popen_shell", r"subprocess\.Popen[^)]*shell\s*=\s*True"),
    ("run_shell", r"subprocess\.run[^)]*shell\s*=\s*True"),
    ("rm_rf", r"rm\s+-rf"),
    ("drop_table", r"\bDROP\s+TABLE\b"),
    ("no_verify", r"--no-verify"),
)

# 하드코딩된 API 키 / secret 추정 패턴
SECRET_PATTERNS: tuple[tuple[str, str], ...] = (
    ("sk_key", r"\bsk-[A-Za-z0-9]{20,}\b"),
    ("pk_key", r"\bpk-[A-Za-z0-9]{20,}\b"),
    ("api_key_assign", r"api[_-]?key\s*=\s*['\"]?[a-zA-Z0-9]{20,}"),
    ("aws_secret", r"AKIA[0-9A-Z]{16}"),
)

# 신규 외부 네트워크 호출 패턴 — 새로 추가되면 차단
NETWORK_PATTERNS: tuple[tuple[str, str], ...] = (
    ("requests_call", r"\brequests\.(get|post|put|delete|patch|request)\s*\("),
    ("httpx_call", r"\bhttpx\.(get|post|put|delete|patch|request|AsyncClient|Client)\s*\("),
    ("urllib_request", r"\burllib\.request\.\w+\s*\("),
    ("fetch_call", r"\bfetch\s*\("),
    ("aiohttp_call", r"\baiohttp\.\w+\s*\("),
)

# diff 라인 임계치 — 이 이상이면 사람이 봐야 한다
MAX_DIFF_LINES = 50


@dataclass
class ValidationResult:
    """안전 게이트 검증 결과.

    approved_for_pr=True 라도 자동 머지가 아니라 Draft PR 제안만 허용된다.
    """

    approved_for_pr: bool
    blocked_reasons: List[str] = field(default_factory=list)


def _diff_line_count(before: str, after: str) -> int:
    """단순 라인 비교 — 추가/제거/수정된 라인 수 추정."""
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    # 단순 길이 차 + 일치하지 않는 라인 수 — 보수적으로 큰 쪽을 택한다
    diff = abs(len(after_lines) - len(before_lines))
    common = min(len(before_lines), len(after_lines))
    mismatched = sum(1 for i in range(common) if before_lines[i] != after_lines[i])
    return diff + mismatched


def _find_added_patterns(
    before: str,
    after: str,
    patterns: tuple[tuple[str, str], ...],
) -> list[str]:
    """after 에는 있지만 before 에는 없는 패턴 매치를 찾는다."""
    added = []
    for name, pat in patterns:
        try:
            after_matches = len(re.findall(pat, after, flags=re.IGNORECASE))
            before_matches = len(re.findall(pat, before, flags=re.IGNORECASE))
            if after_matches > before_matches:
                added.append(name)
        except re.error as e:
            logger.warning(f"regex 오류 {name}: {e}")
    return added


class SafetyGate:
    """제안 + 샌드박스 결과를 받아 다단계 검사를 수행."""

    def validate(
        self,
        proposal: ChangeProposal,
        sandbox: SandboxResult,
    ) -> ValidationResult:
        reasons: List[str] = []

        # 1) critical 위험도 — 자동 거부
        if proposal.risk_level == "critical":
            reasons.append("risk_level=critical: 자동 PR 제안 금지, 사람이 직접 처리해야 함")
            logger.warning(
                f"critical 제안 거부: {proposal.file_path} ({proposal.reason[:80]})"
            )
            # critical 은 다른 검사 결과와 무관하게 즉시 거부
            return ValidationResult(approved_for_pr=False, blocked_reasons=reasons)

        # 2) 샌드박스 통과 여부
        if not sandbox.passed:
            reasons.append(
                f"sandbox 실패 (exit={sandbox.exit_code})"
                + (f": {sandbox.error}" if sandbox.error else "")
            )

        # 3) 위험 패턴 — proposed_code 에서 직접 검사 (before 와 무관하게 등장 자체 금지)
        for name, pat in DANGEROUS_PATTERNS:
            try:
                if re.search(pat, proposal.proposed_code, flags=re.IGNORECASE):
                    # before 에 이미 있던 경우는 신규 추가가 아니므로 제외
                    if not re.search(pat, proposal.current_code, flags=re.IGNORECASE):
                        reasons.append(f"위험 패턴 신규 등장: {name}")
            except re.error as e:
                logger.warning(f"regex 오류 {name}: {e}")

        # 3-b) 하드코딩된 secret
        for name, pat in SECRET_PATTERNS:
            try:
                if re.search(pat, proposal.proposed_code):
                    if not re.search(pat, proposal.current_code):
                        reasons.append(f"하드코딩된 secret 의심: {name}")
            except re.error as e:
                logger.warning(f"regex 오류 {name}: {e}")

        # 4) diff 크기
        diff_lines = _diff_line_count(proposal.current_code, proposal.proposed_code)
        if diff_lines >= MAX_DIFF_LINES:
            reasons.append(
                f"변경 라인 수 {diff_lines} >= {MAX_DIFF_LINES} — 사람 검토 필수"
            )

        # 5) 신규 외부 네트워크 호출
        added_net = _find_added_patterns(
            proposal.current_code, proposal.proposed_code, NETWORK_PATTERNS
        )
        if added_net:
            reasons.append(f"신규 외부 네트워크 호출: {', '.join(added_net)}")

        approved = len(reasons) == 0
        if approved:
            logger.info(
                f"안전 게이트 통과(Draft PR 가능): {proposal.file_path} "
                f"risk={proposal.risk_level} diff={diff_lines}L"
            )
        else:
            logger.warning(
                f"안전 게이트 차단: {proposal.file_path} reasons={reasons}"
            )
        return ValidationResult(approved_for_pr=approved, blocked_reasons=reasons)
