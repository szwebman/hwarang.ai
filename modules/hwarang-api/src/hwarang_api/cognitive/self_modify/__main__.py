"""자체개선 파이프라인 오케스트레이터 진입점.

전체 흐름:
    1. 제안 생성 (hard-block 검사 포함)
    2. critical 위험도면 즉시 거부 + 로그
    3. 샌드박스 격리 테스트
    4. 안전 게이트 검증
    5. 통과 시에만 Draft PR 생성
    6. 모든 단계 감사 로그
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .approval_log import log_proposal
from .change_proposal import generate_proposal, is_hard_blocked
from .pr_creator import PRCreator
from .safety_gate import SafetyGate
from .sandbox_test import SandboxRunner

logger = logging.getLogger(__name__)


def propose_change(
    file_path: str,
    observation: str,
    llm: Any,
    test_command: str = "pytest -x -q",
    create_pr: bool = True,
) -> dict[str, Any]:
    """자체개선 파이프라인 실행.

    Args:
        file_path: 대상 파일 경로
        observation: 관찰된 문제 설명
        llm: LLM 인터페이스 (callable 또는 .generate)
        test_command: 샌드박스 내부에서 실행할 테스트 명령
        create_pr: False 면 dry-run (PR 생성 안 함)

    Returns:
        파이프라인 결과 dict
    """
    base_log: dict[str, Any] = {
        "file_path": file_path,
        "observation": observation[:500],
        "stage": "init",
    }

    # 1) hard-block 사전 검사
    if is_hard_blocked(file_path):
        base_log.update(
            stage="hard_blocked",
            validation_passed=False,
            blocked_reasons=["hard-blocked path"],
            pr_url_if_any=None,
        )
        log_proposal(base_log)
        return {"status": "hard_blocked", "file_path": file_path}

    # 2) 제안 생성
    proposal = generate_proposal(file_path, observation, llm)
    if proposal is None:
        base_log.update(
            stage="proposal_failed",
            validation_passed=False,
            blocked_reasons=["proposal generation failed"],
            pr_url_if_any=None,
        )
        log_proposal(base_log)
        return {"status": "proposal_failed", "file_path": file_path}

    base_log["risk_level"] = proposal.risk_level

    # 3) critical 즉시 거부
    if proposal.risk_level == "critical":
        base_log.update(
            stage="critical_rejected",
            validation_passed=False,
            blocked_reasons=["risk_level=critical"],
            pr_url_if_any=None,
            reason=proposal.reason[:300],
        )
        log_proposal(base_log)
        return {
            "status": "critical_rejected",
            "file_path": file_path,
            "risk_level": "critical",
        }

    # 4) 샌드박스
    try:
        runner = SandboxRunner()
    except Exception as e:
        base_log.update(
            stage="sandbox_init_failed",
            validation_passed=False,
            blocked_reasons=[f"sandbox init: {e}"],
            pr_url_if_any=None,
        )
        log_proposal(base_log)
        return {"status": "sandbox_init_failed", "error": str(e)}

    sandbox_result = runner.run_in_sandbox(proposal, test_command=test_command)

    # 5) 안전 게이트
    gate = SafetyGate()
    validation = gate.validate(proposal, sandbox_result)
    base_log.update(
        sandbox_passed=sandbox_result.passed,
        sandbox_exit_code=sandbox_result.exit_code,
        sandbox_duration_s=sandbox_result.duration_s,
        validation_passed=validation.approved_for_pr,
        blocked_reasons=validation.blocked_reasons,
    )

    if not validation.approved_for_pr:
        base_log["stage"] = "validation_blocked"
        base_log["pr_url_if_any"] = None
        log_proposal(base_log)
        return {
            "status": "validation_blocked",
            "file_path": file_path,
            "blocked_reasons": validation.blocked_reasons,
            "sandbox_passed": sandbox_result.passed,
        }

    # 6) PR 생성 (선택)
    if not create_pr:
        base_log["stage"] = "dry_run_approved"
        base_log["pr_url_if_any"] = None
        log_proposal(base_log)
        return {
            "status": "dry_run_approved",
            "file_path": file_path,
            "risk_level": proposal.risk_level,
            "diff_lines_estimate": _quick_diff(proposal.current_code, proposal.proposed_code),
        }

    creator = PRCreator()
    try:
        pr_result = creator.create_proposal_pr(proposal, sandbox_result, validation)
    except Exception as e:
        logger.exception("PR 생성 중 예외")
        base_log.update(stage="pr_creation_exception", pr_url_if_any=None, error=str(e))
        log_proposal(base_log)
        return {"status": "pr_creation_exception", "error": str(e)}

    base_log.update(
        stage="pr_created" if pr_result.get("pr_url") else "pr_creation_failed",
        pr_url_if_any=pr_result.get("pr_url"),
        branch_name=pr_result.get("branch_name"),
    )
    if pr_result.get("error"):
        base_log["pr_error"] = pr_result["error"]
    log_proposal(base_log)

    return {
        "status": "pr_created" if pr_result.get("pr_url") else "pr_creation_failed",
        "file_path": file_path,
        "pr_url": pr_result.get("pr_url"),
        "branch_name": pr_result.get("branch_name"),
        "error": pr_result.get("error"),
    }


def _quick_diff(before: str, after: str) -> int:
    a = before.splitlines()
    b = after.splitlines()
    return abs(len(a) - len(b)) + sum(
        1 for i in range(min(len(a), len(b))) if a[i] != b[i]
    )
