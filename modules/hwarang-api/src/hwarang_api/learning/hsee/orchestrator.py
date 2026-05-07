"""HSEE Phase 4 — Orchestrator (메인 루프 + 안전장치).

흐름::

    detect_weakness ──► generate_data ──► verify (cross_verifier)
                                              │
                                              ▼
                                   safety_gate.register_artifact
                                              │
                                              ▼
                                   safety_gate.open_draft_pr
                                              │
                                              ▼
                                queue (approved=False — 인간 검토 대기)
                                              │
                                              ▼
                              phase2 weekly cron 픽업 (인간 승인 후에만)

원칙:
    * 자율 학습 활성화 X — 이 모듈은 큐만 만든다
    * 직접 학습 트리거 X — phase2 의 주간 cron 이 ``can_phase2_pickup`` 통과 시 픽업
    * RSI 차단 — orchestrator 가 자기 자신/스케줄러/cognitive 코드 변경 X
    * 한 라운드 안전 상한 (``ABSOLUTE_MAX_PAIRS_PER_ROUND``)

CLI 진입점::

    python -m hwarang_api.learning.hsee.orchestrator
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hwarang_api.learning.hsee import safety_gate
from hwarang_api.learning.hsee.synthetic_generator import (
    ABSOLUTE_MAX_PAIRS_PER_ROUND,
    MAX_PAIRS_PER_DOMAIN,
    MIN_PAIRS_PER_DOMAIN,
    SyntheticPair,
    generate_pairs_for_weakness,
    write_jsonl,
)
from hwarang_api.learning.hsee.weakness_detector import (
    WeaknessSignal,
    detect_weaknesses,
)

logger = logging.getLogger(__name__)


# ─── 출력 경로 ────────────────────────────────────────────────────
# this file: modules/hwarang-api/src/hwarang_api/learning/hsee/orchestrator.py
#   parents[0]=hsee, [1]=learning, [2]=hwarang_api, [3]=src, [4]=hwarang-api
DEFAULT_OUT_ROOT = Path(
    Path(__file__).resolve().parents[4] / "var" / "hsee" / "data"
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _bucket_by_domain(
    weaknesses: list[WeaknessSignal],
) -> dict[str, list[WeaknessSignal]]:
    bucket: dict[str, list[WeaknessSignal]] = {}
    for w in weaknesses:
        bucket.setdefault(w.domain, []).append(w)
    return bucket


# ─── 메인 라운드 ──────────────────────────────────────────────────
async def run_evolution_round(
    top_n_weaknesses: int = 30,
    pairs_per_weakness: int = MIN_PAIRS_PER_DOMAIN,
    max_total_pairs: int = ABSOLUTE_MAX_PAIRS_PER_ROUND,
    out_root: Path | str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """한 사이클 — 약점 탐지 → 데이터 생성 → 검증 → Draft PR 큐 등록.

    Args:
        top_n_weaknesses: detector 가 반환할 약점 패턴 수.
        pairs_per_weakness: 약점당 생성 시도할 페어 수 ([MIN, MAX] clamp).
        max_total_pairs: 한 라운드의 절대 상한 (안전장치).
        out_root: jsonl 저장 루트.
        dry_run: True 면 실제 PR 안 만듦 (기본 True — 안전 우선).

    Returns:
        통계 dict.
    """
    started = _utcnow()

    # 1) 약점 탐지
    weaknesses = await detect_weaknesses(top_n=top_n_weaknesses)
    if not weaknesses:
        return {
            "ok": True,
            "weaknesses": 0,
            "reason": "no_weakness_detected",
            "elapsed_seconds": (_utcnow() - started).total_seconds(),
        }

    # 안전 상한 — 너무 많으면 위쪽만 사용
    pairs_per_weakness = max(
        MIN_PAIRS_PER_DOMAIN, min(MAX_PAIRS_PER_DOMAIN, int(pairs_per_weakness))
    )

    out_dir = Path(out_root) if out_root else DEFAULT_OUT_ROOT
    out_dir.mkdir(parents=True, exist_ok=True)

    by_domain = _bucket_by_domain(weaknesses)
    artifacts: list[dict[str, Any]] = []
    grand_pairs = 0
    grand_verified = 0
    grand_rejected = 0
    halted_for_limit = False

    for domain, sigs in by_domain.items():
        domain_pairs: list[SyntheticPair] = []

        for sig in sigs:
            if grand_pairs >= max_total_pairs:
                halted_for_limit = True
                break
            try:
                pairs = await generate_pairs_for_weakness(
                    sig, n_pairs=pairs_per_weakness
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "HSEE generate failed (%s/%s): %s",
                    domain, sig.query_pattern[:50], exc,
                )
                continue
            domain_pairs.extend(pairs)
            grand_pairs += len(pairs)

        if not domain_pairs:
            continue

        verified = [p for p in domain_pairs if p.verified]
        rejected = [p for p in domain_pairs if not p.verified]
        grand_verified += len(verified)
        grand_rejected += len(rejected)

        # 2) jsonl 저장 (verified 만)
        ts = started.strftime("%Y%m%d_%H%M%S")
        jsonl_path = out_dir / f"hsee_{domain}_{ts}.jsonl"
        write_result = write_jsonl(domain_pairs, jsonl_path, only_verified=True)

        # 3) 보호 경로 변경 없음 확인 (RSI 차단)
        try:
            safety_gate.assert_no_self_modify([str(jsonl_path)])
        except RuntimeError as exc:
            logger.error("HSEE RSI guard tripped: %s", exc)
            continue

        # 4) artifact 등록 + Draft PR
        art = safety_gate.register_artifact(
            domain=domain,
            jsonl_path=str(jsonl_path),
            weakness_count=len(sigs),
            pair_count=len(domain_pairs),
            verified_count=len(verified),
            rejected_count=len(rejected),
            weakness_origins=[s.query_pattern for s in sigs[:20]],
            notes=("dry_run" if dry_run else ""),
        )
        # dry_run 일 때도 큐에는 들어가지만, open_draft_pr 가 실제 gh 호출은
        # 환경변수 HSEE_DRY_RUN 으로 별도 제어 (기본 ON).
        art = safety_gate.open_draft_pr(art)

        artifacts.append(
            {
                "round_id": art.round_id,
                "domain": domain,
                "jsonl": str(jsonl_path),
                "pairs": len(domain_pairs),
                "verified": len(verified),
                "rejected": len(rejected),
                "pr_url": art.pr_url,
                "approved": art.approved,
                "write": write_result,
            }
        )

        if grand_pairs >= max_total_pairs:
            halted_for_limit = True
            break

    return {
        "ok": True,
        "started_at": started.isoformat(),
        "elapsed_seconds": (_utcnow() - started).total_seconds(),
        "weaknesses_detected": len(weaknesses),
        "domains": list(by_domain.keys()),
        "total_pairs": grand_pairs,
        "verified": grand_verified,
        "rejected": grand_rejected,
        "halted_for_limit": halted_for_limit,
        "artifacts": artifacts,
        "phase2_pickup_blocked_until_approval": True,
    }


# ─── phase2 픽업 헬퍼 (cron 이 호출) ──────────────────────────────
def list_approved_for_phase2() -> list[dict[str, Any]]:
    """phase2 주간 cron 이 호출 — 승인된 artifact 목록.

    ``safety_gate.can_phase2_pickup`` 통과분만 반환.
    """
    pending = safety_gate.list_pending()
    # list_pending 은 approved=False 만 반환하므로, 승인 후엔 directory 직접 스캔
    out: list[dict[str, Any]] = []
    if not safety_gate.QUEUE_ROOT.exists():
        return out
    import json
    for fp in safety_gate.QUEUE_ROOT.glob("*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if data.get("approved") and safety_gate.can_phase2_pickup(
                data.get("round_id", "")
            ):
                out.append(data)
        except Exception:  # noqa: BLE001
            continue
    # 디버그: pending 카운트 동시 반환을 원하면 호출자가 list_pending 별도 호출
    _ = pending
    return out


# ─── CLI ──────────────────────────────────────────────────────────
async def _amain() -> None:
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(description="HSEE Phase 4 orchestrator")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--pairs-per-weakness", type=int, default=MIN_PAIRS_PER_DOMAIN)
    parser.add_argument("--max-total", type=int, default=ABSOLUTE_MAX_PAIRS_PER_ROUND)
    parser.add_argument("--no-dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    result = await run_evolution_round(
        top_n_weaknesses=args.top_n,
        pairs_per_weakness=args.pairs_per_weakness,
        max_total_pairs=args.max_total,
        dry_run=not args.no_dry_run,
    )
    print(_json.dumps(result, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    asyncio.run(_amain())


__all__ = [
    "run_evolution_round",
    "list_approved_for_phase2",
    "main",
]


if __name__ == "__main__":
    main()
