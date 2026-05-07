"""HSEE Phase 4 — Safety Gate (Self-Modify 차단 + Draft PR only).

원칙 (memory: hcl_phase9_deep_cognition):
    * RSI (Recursive Self-Improvement) 차단 — orchestrator 가 자기 자신을 수정 X
    * Self-Modify 는 Draft PR 만 — human approval 없이 머지 절대 금지
    * 자동 머지 X, 자동 push to main X, 자동 LoRA swap X

이 모듈이 하는 일:
    1. ``register_artifact`` — 합성 데이터/LoRA 변경분을 큐에 등록 + 메타 기록
    2. ``open_draft_pr`` — GitHub CLI(gh) 로 Draft PR 만 생성 (mock 폴백 있음)
    3. ``can_phase2_pickup`` — 인간 승인(approved=True) 전에는 phase2 cron 픽업 차단

저장 위치 (스켈레톤): ``modules/hwarang-api/var/hsee/queue/<round_id>.json``
실제 운용에서는 별도 테이블/큐로 옮길 수 있다.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ─── 디스크 큐 위치 ────────────────────────────────────────────────
# this file: modules/hwarang-api/src/hwarang_api/learning/hsee/safety_gate.py
#   parents[0]=hsee, [1]=learning, [2]=hwarang_api, [3]=src, [4]=hwarang-api
QUEUE_ROOT = Path(
    os.getenv(
        "HSEE_QUEUE_DIR",
        str(Path(__file__).resolve().parents[4] / "var" / "hsee" / "queue"),
    )
)

# 안전 스위치 — 실제 PR 을 안 만들고 dry-run 만 (기본 ON)
HSEE_DRY_RUN = os.getenv("HSEE_DRY_RUN", "1").lower() in ("1", "true", "yes")

# RSI 차단 — orchestrator 가 다음 경로를 수정하려 하면 즉시 거부
PROTECTED_PATHS: tuple[str, ...] = (
    "modules/hwarang-api/src/hwarang_api/learning/hsee/",
    "modules/hwarang-api/src/hwarang_api/cognitive/",  # 메타인지 보호
    "modules/hwarang-api/src/hwarang_api/workers/hlkm_scheduler.py",
)


@dataclass
class Artifact:
    """phase 4 출력물 — 합성 데이터 jsonl + 메타."""

    round_id: str
    domain: str
    jsonl_path: str
    weakness_count: int
    pair_count: int
    verified_count: int
    rejected_count: int
    weakness_origins: list[str] = field(default_factory=list)
    generator: str = "hsee_phase4"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    pr_url: str | None = None
    pr_number: int | None = None
    approved: bool = False  # human 이 PR 머지/체크박스 클릭해야 True
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        return d


# ─── RSI 가드 ─────────────────────────────────────────────────────
def is_protected_path(path: str | Path) -> bool:
    """PR 의 변경 파일이 보호 경로에 닿는지 확인."""
    s = str(path).replace("\\", "/")
    return any(p in s for p in PROTECTED_PATHS)


def assert_no_self_modify(changed_paths: list[str]) -> None:
    """변경 파일에 보호 경로가 있으면 즉시 ``RuntimeError``.

    orchestrator 는 데이터 (jsonl) 만 만든다. 코드 변경은 별도 인간 PR 만.
    """
    bad = [p for p in changed_paths if is_protected_path(p)]
    if bad:
        raise RuntimeError(
            f"HSEE safety_gate: self-modify blocked (RSI). protected: {bad}"
        )


# ─── 큐 I/O ───────────────────────────────────────────────────────
def _queue_path(round_id: str) -> Path:
    return QUEUE_ROOT / f"{round_id}.json"


def register_artifact(
    domain: str,
    jsonl_path: str,
    weakness_count: int,
    pair_count: int,
    verified_count: int,
    rejected_count: int,
    weakness_origins: list[str] | None = None,
    notes: str = "",
) -> Artifact:
    """합성 데이터 산출물을 큐에 등록.

    아직 ``approved=False`` — phase2 cron 은 이 상태에서 픽업 X.
    """
    QUEUE_ROOT.mkdir(parents=True, exist_ok=True)
    art = Artifact(
        round_id=uuid.uuid4().hex[:12],
        domain=domain,
        jsonl_path=str(jsonl_path),
        weakness_count=int(weakness_count),
        pair_count=int(pair_count),
        verified_count=int(verified_count),
        rejected_count=int(rejected_count),
        weakness_origins=list(weakness_origins or []),
        notes=notes,
    )
    _queue_path(art.round_id).write_text(
        json.dumps(art.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("HSEE artifact queued: %s domain=%s pairs=%d", art.round_id, domain, pair_count)
    return art


def list_pending() -> list[dict[str, Any]]:
    """승인 대기 중인 artifact (approved=False)."""
    QUEUE_ROOT.mkdir(parents=True, exist_ok=True)
    out: list[dict[str, Any]] = []
    for fp in QUEUE_ROOT.glob("*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if not data.get("approved", False):
                out.append(data)
        except Exception:  # noqa: BLE001
            continue
    return out


def can_phase2_pickup(round_id: str) -> bool:
    """phase2 주간 cron 이 이 artifact 를 학습 입력으로 가져갈 수 있는지.

    ``approved=True`` (인간이 PR 머지 후 체크) 일 때만 True.
    """
    p = _queue_path(round_id)
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return bool(data.get("approved", False))
    except Exception:  # noqa: BLE001
        return False


def mark_approved(round_id: str, approved: bool = True) -> bool:
    """관리자가 PR 검토 후 승인 (CLI/관리자 UI 용)."""
    p = _queue_path(round_id)
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        data["approved"] = bool(approved)
        p.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("mark_approved failed: %s", exc)
        return False


# ─── Draft PR 생성 (gh CLI) ───────────────────────────────────────
PR_BODY_TEMPLATE = """## HSEE Phase 4 — 합성 학습 데이터 (Draft, 검토 필요)

**round_id**: `{round_id}`
**domain**: {domain}
**generator**: {generator}
**created_at**: {created_at}

### 약점 출처 (weakness origins)
{origins}

### 산출
- jsonl: `{jsonl_path}`
- 약점 패턴 수: {weakness_count}
- 생성 페어: {pair_count}
- 검증 통과: {verified_count}
- 폐기: {rejected_count}

### 검증
- cross_verifier (HLKM Trusted Source) 통과분만 jsonl 에 기록
- system prompt 강제 (우회 차단)
- RSI 차단: 보호 경로 변경 없음

### 다음 단계 (인간 승인 필요)
- [ ] jsonl 샘플링 검토 (최소 10 건)
- [ ] system prompt 일치 확인
- [ ] 도메인 라벨 정합성 확인
- [ ] 승인 시 `mark_approved({round_id})` 호출 → phase2 cron 픽업

자동 머지 절대 금지. Draft PR 그대로 유지.
"""


def open_draft_pr(art: Artifact, branch_prefix: str = "hsee") -> Artifact:
    """Draft PR 생성. dry-run / gh 미설치 시 mock URL.

    중요: 실제 gh PR 은 ``HSEE_DRY_RUN=0`` + ``gh`` 가 설치돼 있을 때만.
    이 함수는 코드 파일을 직접 수정 X — jsonl 경로만 PR description 에 기록.
    """
    body = PR_BODY_TEMPLATE.format(
        round_id=art.round_id,
        domain=art.domain,
        generator=art.generator,
        created_at=art.created_at.isoformat(),
        jsonl_path=art.jsonl_path,
        weakness_count=art.weakness_count,
        pair_count=art.pair_count,
        verified_count=art.verified_count,
        rejected_count=art.rejected_count,
        origins="\n".join(f"- {o}" for o in art.weakness_origins[:20]) or "- (없음)",
    )
    title = f"[HSEE/Draft] phase4 합성데이터 {art.domain} round={art.round_id}"

    if HSEE_DRY_RUN or not shutil.which("gh"):
        art.pr_url = f"mock://draft-pr/{art.round_id}"
        art.pr_number = None
        art.notes = (art.notes + " | dry_run").strip(" |")
        _queue_path(art.round_id).write_text(
            json.dumps(art.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("HSEE draft PR (dry-run) %s → %s", art.round_id, art.pr_url)
        return art

    # 실제 gh CLI 실행 (스켈레톤 — 실제 운용에서는 branch push 단계 추가 필요)
    try:
        cmd = [
            "gh", "pr", "create",
            "--draft",
            "--title", title,
            "--body", body,
        ]
        out = subprocess.run(
            cmd, check=True, capture_output=True, text=True, timeout=30
        )
        art.pr_url = out.stdout.strip()
        _queue_path(art.round_id).write_text(
            json.dumps(art.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("HSEE draft PR opened: %s", art.pr_url)
        return art
    except Exception as exc:  # noqa: BLE001
        logger.warning("gh pr create failed: %s — falling back to mock URL", exc)
        art.pr_url = f"mock://draft-pr/{art.round_id}"
        art.notes = (art.notes + " | gh_failed").strip(" |")
        _queue_path(art.round_id).write_text(
            json.dumps(art.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return art


__all__ = [
    "Artifact",
    "PROTECTED_PATHS",
    "QUEUE_ROOT",
    "is_protected_path",
    "assert_no_self_modify",
    "register_artifact",
    "list_pending",
    "can_phase2_pickup",
    "mark_approved",
    "open_draft_pr",
]
