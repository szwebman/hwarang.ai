"""평가셋 자동 구성 — 학습에 안 쓰인 high-quality CodePair 중 100개.

매 라운드 시작 전:

1. CodePair 중 ``executionStatus=passed`` AND ``qualityScore≥0.7`` AND
   (``isEvaluation=True`` 가능하면 우선) 100개 선정
2. 평가셋 jsonl 로 디스크 저장 — 라운드 간 unchanged 라서 비교 가능
3. 부족하면 학습 데이터 (isUsedInLora=True) 도 fallback 으로 흡수

호출:

    eval_path = await build_or_load_eval_set(domain="code")

실패 시 빈 문자열 반환. ``lora_evaluator`` 가 그걸 보고 0.5 로 fallback.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


# 평가셋 jsonl 저장 디렉토리. 라운드 간 변경되지 않으므로 고정 경로.
EVAL_SET_DIR = os.getenv("HWARANG_EVAL_SET_DIR", "/var/hwarang/eval_sets")
# 평가셋 크기 — 너무 크면 매 라운드 평가가 오래 걸리고, 너무 작으면 분산 큼.
EVAL_SET_SIZE = int(os.getenv("HWARANG_EVAL_MAX_SAMPLES", "100"))


def _is_db_ready() -> bool:
    return getattr(prisma, "is_connected", lambda: False)()


def _eval_path(domain: str) -> Path:
    Path(EVAL_SET_DIR).mkdir(parents=True, exist_ok=True)
    return Path(EVAL_SET_DIR) / f"{domain}_eval.jsonl"


async def build_or_load_eval_set(domain: str = "code") -> str:
    """평가셋 jsonl 경로 반환. 없으면 신규 구성.

    반환: 절대 경로 문자열. 구성 실패 시 빈 문자열.
    """
    eval_path = _eval_path(domain)

    # 이미 있으면 그대로 (라운드 간 unchanged 보장)
    if eval_path.exists() and eval_path.stat().st_size > 0:
        return str(eval_path)

    if not _is_db_ready():
        logger.warning("eval_set_builder: DB unavailable, skip 구성")
        return ""

    pairs = await _select_pairs(prefer_evaluation=True)

    # 부족하면 학습된 페어도 흡수
    if len(pairs) < max(30, EVAL_SET_SIZE // 3):
        logger.warning(
            "평가셋 부족 (%d/%d) — 학습된 페어 일부도 사용",
            len(pairs),
            EVAL_SET_SIZE,
        )
        pairs = await _select_pairs(prefer_evaluation=False)

    if not pairs:
        logger.warning("평가셋 구성 실패 — high-quality CodePair 가 없음")
        return ""

    # JSONL 저장
    with open(eval_path, "w", encoding="utf-8") as f:
        for p in pairs:
            row = {
                "id": getattr(p, "id", None),
                "instruction": getattr(p, "instruction", "") or "",
                "expected": getattr(p, "response", "") or "",
                "language": getattr(p, "language", None),
                "framework": getattr(p, "framework", None),
            }
            if not row["instruction"] or not row["expected"]:
                continue
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    logger.info("평가셋 구성 완료: %s (%d건)", eval_path, len(pairs))
    return str(eval_path)


async def _select_pairs(prefer_evaluation: bool) -> list:
    """CodePair 선별. ``isEvaluation`` 컬럼이 없을 수도 있어서 fallback 처리."""
    base_where: dict = {
        "executionStatus": "passed",
        "qualityScore": {"gte": 0.7},
    }

    # isEvaluation 우선 — 컬럼 미존재 환경에서도 깨지지 않게 try-fallback
    if prefer_evaluation:
        try:
            where = dict(base_where)
            where["isEvaluation"] = True
            pairs = await prisma.codepair.find_many(
                where=where,
                take=EVAL_SET_SIZE,
                order={"qualityScore": "desc"},
            )
            if pairs:
                return list(pairs)
        except Exception as exc:  # noqa: BLE001
            logger.debug("isEvaluation 필터 실패 (스키마 미반영?): %s", exc)

        # 다음 fallback: 학습 안 쓰인 페어 우선
        try:
            where = dict(base_where)
            where["isUsedInLora"] = False
            pairs = await prisma.codepair.find_many(
                where=where,
                take=EVAL_SET_SIZE,
                order={"qualityScore": "desc"},
            )
            if pairs:
                return list(pairs)
        except Exception as exc:  # noqa: BLE001
            logger.debug("isUsedInLora=False 조회 실패: %s", exc)

    # 마지막: high-quality 만 — 학습됐든 안 됐든
    try:
        pairs = await prisma.codepair.find_many(
            where=base_where,
            take=EVAL_SET_SIZE,
            order={"qualityScore": "desc"},
        )
        return list(pairs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("CodePair.find_many 실패: %s", exc)
        return []


async def rebuild_eval_set(domain: str = "code") -> str:
    """기존 평가셋 삭제 후 재구성."""
    eval_path = _eval_path(domain)
    if eval_path.exists():
        try:
            eval_path.unlink()
        except OSError as exc:
            logger.warning("기존 평가셋 삭제 실패: %s", exc)
    return await build_or_load_eval_set(domain=domain)


__all__ = [
    "EVAL_SET_DIR",
    "EVAL_SET_SIZE",
    "build_or_load_eval_set",
    "rebuild_eval_set",
]
