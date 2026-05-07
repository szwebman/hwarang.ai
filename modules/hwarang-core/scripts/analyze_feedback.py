"""HSEE Phase 1 — RLHFFeedback 분석 스크립트.

지난 N일 동안 수집된 ``RLHFFeedback`` 레코드의 통계를 출력하고,
DPO 학습 데이터로 변환할 수 있는 저품질 페어를 미리 보여준다.

명시 피드백(👍/👎) 은 거의 없을 가능성이 높으므로 (위험성 때문에 UI 제거),
주로 암묵 신호(comment 가 ``[implicit:*]`` 으로 시작)를 분석한다.

사용법::

    python -m hwarang_core.scripts.analyze_feedback --days 7 --preview-pairs 20
    python modules/hwarang-core/scripts/analyze_feedback.py --days 7

DB 접근:
    환경변수 ``DATABASE_URL`` (Postgres) 또는 ``HWARANG_API_DB_URL``.
    psycopg2 또는 asyncpg 가 있으면 사용. 없으면 prisma client (api 모듈) 폴백.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional


# ────────────────────────────────────────────────────────────
# 데이터 클래스
# ────────────────────────────────────────────────────────────
@dataclass
class FeedbackRow:
    id: str
    user_id: str
    message_id: Optional[str]
    domain: Optional[str]
    model_name: Optional[str]
    lora_name: Optional[str]
    rating: Optional[int]
    edit_distance: Optional[float]
    followup_msg: Optional[str]
    is_satisfied: Optional[bool]
    created_at: datetime


# ────────────────────────────────────────────────────────────
# DB 어댑터 — 우선 psycopg, 없으면 prisma_client(asyncio) 폴백
# ────────────────────────────────────────────────────────────
def _fetch_with_psycopg(database_url: str, since: datetime) -> list[FeedbackRow]:
    try:
        import psycopg  # type: ignore
    except ImportError:
        try:
            import psycopg2 as psycopg  # type: ignore
        except ImportError:
            return []

    rows: list[FeedbackRow] = []
    with psycopg.connect(database_url) as conn:  # type: ignore[arg-type]
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, "userId", "messageId", domain, "modelName", "loraName",
                       rating, "editDistance", "followupMsg", "isSatisfied", "createdAt"
                FROM "RLHFFeedback"
                WHERE "createdAt" >= %s
                ORDER BY "createdAt" DESC
                """,
                (since,),
            )
            for r in cur.fetchall():
                rows.append(
                    FeedbackRow(
                        id=r[0],
                        user_id=r[1],
                        message_id=r[2],
                        domain=r[3],
                        model_name=r[4],
                        lora_name=r[5],
                        rating=r[6],
                        edit_distance=r[7],
                        followup_msg=r[8],
                        is_satisfied=r[9],
                        created_at=r[10],
                    )
                )
    return rows


async def _fetch_with_prisma(since: datetime) -> list[FeedbackRow]:
    """hwarang_api 의 prisma client 가 사용 가능하면 사용."""
    try:
        # 워크스페이스에 hwarang_api 가 install 되어 있어야 함.
        from hwarang_api.db import prisma  # type: ignore
    except Exception:
        return []
    if not getattr(prisma, "is_connected", lambda: False)():
        try:
            await prisma.connect()
        except Exception:
            return []

    rows = await prisma.rlhffeedback.find_many(
        where={"createdAt": {"gte": since}},
        order=[{"createdAt": "desc"}],
    )
    out: list[FeedbackRow] = []
    for r in rows:
        out.append(
            FeedbackRow(
                id=getattr(r, "id", ""),
                user_id=getattr(r, "userId", ""),
                message_id=getattr(r, "messageId", None),
                domain=getattr(r, "domain", None),
                model_name=getattr(r, "modelName", None),
                lora_name=getattr(r, "loraName", None),
                rating=getattr(r, "rating", None),
                edit_distance=getattr(r, "editDistance", None),
                followup_msg=getattr(r, "followupMsg", None),
                is_satisfied=getattr(r, "isSatisfied", None),
                created_at=getattr(r, "createdAt", since),
            )
        )
    return out


def fetch_recent(days: int) -> list[FeedbackRow]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    db_url = os.getenv("DATABASE_URL") or os.getenv("HWARANG_API_DB_URL")
    if db_url:
        try:
            return _fetch_with_psycopg(db_url, since)
        except Exception as e:
            print(f"[warn] psycopg 실패: {e}", file=sys.stderr)
    # 폴백 — prisma async
    try:
        import asyncio

        return asyncio.run(_fetch_with_prisma(since))
    except Exception as e:
        print(f"[warn] prisma 폴백 실패: {e}", file=sys.stderr)
        return []


# ────────────────────────────────────────────────────────────
# 분석
# ────────────────────────────────────────────────────────────
def classify_signal(row: FeedbackRow) -> str:
    """rating + comment 패턴 → 신호 종류."""
    c = row.followup_msg or ""
    if c.startswith("[implicit:apply]"):
        return "implicit_apply"
    if c.startswith("[implicit:copy]"):
        return "implicit_copy"
    if c.startswith("[implicit:reject]"):
        return "implicit_reject"
    if c.startswith("[implicit:followup]"):
        return "implicit_negative_followup"
    if c.startswith("[implicit:edit_distance"):
        return "implicit_edit_distance"
    if row.rating == 1:
        return "explicit_positive"  # GRPO 라우트 경유
    if row.rating == -1:
        return "explicit_negative"
    return "unknown"


def summarize(rows: Iterable[FeedbackRow]) -> dict[str, Any]:
    total = 0
    by_signal: dict[str, int] = collections.Counter()
    by_domain: dict[str, dict[str, int]] = collections.defaultdict(
        lambda: collections.Counter()
    )
    by_model: dict[str, dict[str, int]] = collections.defaultdict(
        lambda: collections.Counter()
    )
    edit_distances: list[float] = []
    pos_count = 0
    neg_count = 0

    for r in rows:
        total += 1
        sig = classify_signal(r)
        by_signal[sig] += 1
        domain = r.domain or "general"
        model = r.model_name or "unknown"
        by_domain[domain][sig] += 1
        by_model[model][sig] += 1

        if r.edit_distance is not None:
            edit_distances.append(float(r.edit_distance))

        if r.is_satisfied is True or r.rating == 1:
            pos_count += 1
        elif r.is_satisfied is False or r.rating == -1:
            neg_count += 1

    avg_dist = (
        sum(edit_distances) / len(edit_distances) if edit_distances else None
    )

    return {
        "total": total,
        "by_signal": dict(by_signal),
        "positive_count": pos_count,
        "negative_count": neg_count,
        "positive_ratio": (pos_count / total) if total else 0.0,
        "negative_ratio": (neg_count / total) if total else 0.0,
        "avg_edit_distance": avg_dist,
        "by_domain": {
            d: dict(sigs) for d, sigs in by_domain.items()
        },
        "by_model": {
            m: dict(sigs) for m, sigs in by_model.items()
        },
    }


# ────────────────────────────────────────────────────────────
# DPO preview — negative 페어 추출 (실제 학습 트리거는 별도 스크립트)
# ────────────────────────────────────────────────────────────
def preview_dpo_pairs(rows: list[FeedbackRow], limit: int = 20) -> list[dict[str, Any]]:
    """저품질 (rejected) 후보 메시지 페어 미리보기.

    실제 DPO 변환에는 messageId → ChatMessage 의 prompt/response 조회가 필요하므로
    여기서는 ``followupMsg`` 만 첨부해서 patch 후보 형태로 보여준다.
    """
    rejected = [
        r
        for r in rows
        if r.is_satisfied is False
        or r.rating == -1
        or (r.followup_msg or "").startswith("[implicit:followup]")
        or (r.followup_msg or "").startswith("[implicit:reject]")
    ]
    # 0.1 배만 추출 (max=limit)
    take = max(1, min(limit, max(1, len(rejected) // 10)))
    sample = rejected[:take]
    return [
        {
            "feedback_id": r.id,
            "message_id": r.message_id,
            "domain": r.domain,
            "model": r.model_name,
            "lora": r.lora_name,
            "signal": classify_signal(r),
            "rating": r.rating,
            "edit_distance": r.edit_distance,
            "followup_excerpt": (r.followup_msg or "")[:160],
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in sample
    ]


# ────────────────────────────────────────────────────────────
# main
# ────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument(
        "--preview-pairs",
        type=int,
        default=20,
        help="DPO 페어 미리보기 최대 개수",
    )
    parser.add_argument(
        "--json", action="store_true", help="결과를 JSON 한 덩어리로 출력"
    )
    args = parser.parse_args()

    print(f"[analyze_feedback] 최근 {args.days}일 RLHFFeedback 조회 중...")
    rows = fetch_recent(args.days)
    print(f"[analyze_feedback] {len(rows)} rows 로드됨")

    summary = summarize(rows)
    pairs = preview_dpo_pairs(rows, limit=args.preview_pairs)

    if args.json:
        print(
            json.dumps(
                {"summary": summary, "dpo_preview": pairs},
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        return 0

    # 사람이 보기 좋은 출력
    print("\n=== 요약 ===")
    print(f"  총 레코드: {summary['total']}")
    print(
        f"  긍정 {summary['positive_count']} ({summary['positive_ratio']:.1%}) / "
        f"부정 {summary['negative_count']} ({summary['negative_ratio']:.1%})"
    )
    if summary["avg_edit_distance"] is not None:
        print(f"  평균 edit distance: {summary['avg_edit_distance']:.3f}")

    print("\n=== 신호 종류별 ===")
    for sig, n in sorted(summary["by_signal"].items(), key=lambda x: -x[1]):
        print(f"  {sig:32s} {n}")

    print("\n=== 도메인별 ===")
    for domain, sigs in sorted(
        summary["by_domain"].items(),
        key=lambda x: -sum(x[1].values()),
    ):
        total = sum(sigs.values())
        print(f"  [{domain}] total={total}")
        for s, n in sorted(sigs.items(), key=lambda x: -x[1]):
            print(f"    {s:32s} {n}")

    print("\n=== 모델별 ===")
    for model, sigs in sorted(
        summary["by_model"].items(),
        key=lambda x: -sum(x[1].values()),
    ):
        total = sum(sigs.values())
        print(f"  [{model}] total={total}")

    print(f"\n=== DPO 페어 미리보기 (max {args.preview_pairs}, 0.1배) ===")
    for p in pairs:
        print(
            f"  - {p['signal']:28s} domain={p['domain']:8s} "
            f"model={p['model']:18s} dist={p['edit_distance']}"
        )
        excerpt = p["followup_excerpt"]
        if excerpt:
            print(f"      followup: {excerpt}")

    print("\n* 실제 DPO 학습 트리거는 별도 스크립트 (auto_trainer) 가 담당.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
