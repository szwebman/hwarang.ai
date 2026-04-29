"""GitHub Draft PR 생성기 (제안만, 절대 머지 안 함).

원칙:
    - 항상 --draft 로 생성 — 자동 머지 우회 불가
    - HWARANG_SELF_MODIFY_ENABLED=1 환경변수가 없으면 PR 생성 거부
    - validation.approved_for_pr=False 면 즉시 raise (assert)
    - gh CLI 미설치 시 graceful 에러 반환
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import shutil
import subprocess
import uuid
from typing import Any, Optional

from .change_proposal import ChangeProposal, is_hard_blocked
from .safety_gate import ValidationResult
from .sandbox_test import SandboxResult, _find_repo_root

logger = logging.getLogger(__name__)


ENV_ENABLE_FLAG = "HWARANG_SELF_MODIFY_ENABLED"
ENV_REPO = "HWARANG_SELF_MODIFY_REPO"


class PRCreator:
    """Draft GitHub PR 생성. 자동 머지 절대 금지."""

    def __init__(self, repo_root: Optional[str] = None):
        self.repo_root = repo_root or (
            str(_find_repo_root()) if _find_repo_root() else None
        )

    def create_proposal_pr(
        self,
        proposal: ChangeProposal,
        sandbox: SandboxResult,
        validation: ValidationResult,
    ) -> dict[str, Any]:
        """검증된 제안을 기반으로 Draft PR 생성.

        Returns:
            성공 시: {"pr_url": str, "branch_name": str}
            실패 시: {"error": str, "branch_name": str | None}
        """
        # 1) 강제 assertion — approved_for_pr=False 면 절대 진행 금지
        if not validation.approved_for_pr:
            raise RuntimeError(
                "validation.approved_for_pr=False — PR 생성 거부 "
                f"(reasons={validation.blocked_reasons})"
            )

        # 2) ENV gate — 활성화되지 않았으면 거부
        if os.getenv(ENV_ENABLE_FLAG) != "1":
            logger.warning(
                f"{ENV_ENABLE_FLAG} != '1' — PR 생성 거부. 환경변수 설정 필요."
            )
            return {
                "error": f"{ENV_ENABLE_FLAG} 환경변수가 '1'로 설정되어야 한다",
                "branch_name": None,
            }

        # 3) 한 번 더 hard-block 검사 (방어 다층화)
        if is_hard_blocked(proposal.file_path):
            logger.error(f"PR 단계 hard-block 차단: {proposal.file_path}")
            return {
                "error": "hard-blocked path — PR 생성 거부",
                "branch_name": None,
            }

        # 4) gh CLI 존재 확인
        if shutil.which("gh") is None:
            logger.error("gh CLI 미설치 — PR 생성 불가")
            return {"error": "gh CLI not installed", "branch_name": None}

        if self.repo_root is None:
            return {"error": "git repo root not found", "branch_name": None}

        # 5) 브랜치 이름 생성
        date_str = _dt.datetime.utcnow().strftime("%Y%m%d")
        short_uuid = uuid.uuid4().hex[:8]
        branch_name = f"hwarang-self-modify/{date_str}-{short_uuid}"

        try:
            # 6) 새 브랜치 체크아웃
            r = subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if r.returncode != 0:
                return {
                    "error": f"branch checkout 실패: {r.stderr}",
                    "branch_name": branch_name,
                }

            # 7) 변경 적용
            from pathlib import Path

            target = Path(self.repo_root) / proposal.file_path
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(proposal.proposed_code, encoding="utf-8")
            except Exception as e:
                self._abort_branch(branch_name)
                return {"error": f"파일 쓰기 실패: {e}", "branch_name": branch_name}

            # 8) 커밋 — 본문에 자동제안 / 인간검토 필수 표시
            commit_msg = (
                f"[자동 제안] {proposal.file_path} 개선\n\n"
                f"{proposal.reason}\n\n"
                "주의: 화랑 자체개선 시스템이 생성한 제안이다. 반드시 사람이 검토 후 머지."
            )
            subprocess.run(
                ["git", "add", proposal.file_path],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            r = subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if r.returncode != 0:
                self._abort_branch(branch_name)
                return {
                    "error": f"git commit 실패: {r.stderr}",
                    "branch_name": branch_name,
                }

            # 9) 원격 push
            r = subprocess.run(
                ["git", "push", "-u", "origin", branch_name],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if r.returncode != 0:
                self._abort_branch(branch_name)
                return {
                    "error": f"git push 실패: {r.stderr}",
                    "branch_name": branch_name,
                }

            # 10) gh pr create — 항상 --draft, 라벨로 명시
            title = f"[자동 제안] {proposal.file_path} 개선"
            body = self._build_body(proposal, sandbox)
            pr_cmd = [
                "gh",
                "pr",
                "create",
                "--title",
                title,
                "--body",
                body,
                "--label",
                "self-modify-proposal",
                "--label",
                "needs-human-review",
                "--draft",
            ]
            repo_env = os.getenv(ENV_REPO)
            if repo_env:
                pr_cmd.extend(["--repo", repo_env])

            r = subprocess.run(
                pr_cmd,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if r.returncode != 0:
                return {
                    "error": f"gh pr create 실패: {r.stderr}",
                    "branch_name": branch_name,
                }
            pr_url = (r.stdout or "").strip().splitlines()[-1] if r.stdout else ""
            logger.info(f"Draft PR 생성됨: {pr_url} (branch={branch_name})")
            return {"pr_url": pr_url, "branch_name": branch_name}
        except subprocess.TimeoutExpired as e:
            return {"error": f"subprocess timeout: {e}", "branch_name": branch_name}
        except Exception as e:
            logger.exception("PR 생성 중 예외")
            return {"error": str(e), "branch_name": branch_name}

    def _abort_branch(self, branch_name: str) -> None:
        """실패 시 브랜치 정리(원래 브랜치로 복귀 시도)."""
        try:
            subprocess.run(
                ["git", "checkout", "-"],
                cwd=self.repo_root,
                capture_output=True,
                timeout=15,
            )
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                cwd=self.repo_root,
                capture_output=True,
                timeout=15,
            )
        except Exception as e:
            logger.warning(f"브랜치 정리 실패 {branch_name}: {e}")

    def _build_body(self, proposal: ChangeProposal, sandbox: SandboxResult) -> str:
        """PR 본문 (한국어). 머지 금지 경고 포함."""
        return (
            "## 제안 이유\n"
            f"{proposal.reason}\n\n"
            "## 위험도\n"
            f"`{proposal.risk_level}`\n\n"
            "## 예상 이점\n"
            f"{proposal.expected_benefit}\n\n"
            "## 샌드박스 테스트 결과\n"
            f"- 통과: `{sandbox.passed}`\n"
            f"- exit_code: `{sandbox.exit_code}`\n"
            f"- duration: `{sandbox.duration_s:.2f}s`\n"
            + (f"- error: `{sandbox.error}`\n" if sandbox.error else "")
            + "\n"
            "## 경고\n"
            "**자동 머지 금지. 반드시 사람이 검토 후 머지.**\n"
            "이 PR 은 화랑 자체개선 시스템이 생성한 제안이며, Draft 상태로 유지된다.\n"
            "검토자 체크리스트:\n"
            "- [ ] 변경 사유가 타당한가?\n"
            "- [ ] 위험 패턴/Secret 이 없는가?\n"
            "- [ ] 테스트가 충분한가?\n"
            "- [ ] 보안/인증/결제 경계를 침범하지 않는가?\n\n"
            "---\n"
            "🤖 화랑 자체개선 시스템 - 인간 검토 필수\n"
        )
