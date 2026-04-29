"""화랑 자체개선(Self-Modifying Code) 시스템.

위험성 경고:
    이 패키지는 LLM이 자신의 코드 변경을 "제안"하도록 한다.
    절대 자동 머지하지 않는다. 모든 변경은 GitHub Draft PR로 제안되며,
    사람이 직접 검토 후 머지해야 한다.

다층 안전 게이트:
    1. ChangeProposal — Hard-block 경로 차단
    2. analyze_risk — 자동 위험도 상향 조정
    3. SandboxRunner — git worktree 격리 + 테스트
    4. SafetyGate — 위험 패턴/diff 크기/네트워크 호출 검사
    5. PRCreator — 항상 --draft, ENV gate 필수

ENV 변수:
    HWARANG_SELF_MODIFY_ENABLED — '1'이어야 PR 생성됨 (기본 off)
    HWARANG_ADMIN_TOKEN — 관리자 인증
    HWARANG_SELF_MODIFY_REPO — 대상 GitHub repo
"""

from .change_proposal import ChangeProposal, generate_proposal, analyze_risk
from .sandbox_test import SandboxRunner, SandboxResult
from .safety_gate import SafetyGate, ValidationResult
from .pr_creator import PRCreator
from .approval_log import log_proposal, recent_proposals

__all__ = [
    "ChangeProposal",
    "generate_proposal",
    "analyze_risk",
    "SandboxRunner",
    "SandboxResult",
    "SafetyGate",
    "ValidationResult",
    "PRCreator",
    "log_proposal",
    "recent_proposals",
]
