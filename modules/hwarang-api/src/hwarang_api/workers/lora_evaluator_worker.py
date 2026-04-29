"""LoRA 평가 전용 워커 — 라운드 완료 후 큐에서 fetch.

매 30초 폴링:

* ``Round.status == COMPLETED`` AND ``qualityScore IS NULL``
  AND ``completedAt < now()-2min`` (병합/업로드가 끝나길 기다리려는 grace)
* 위 조건 만족하는 라운드 1개씩 ``validate_completed_round`` 호출

별도 프로세스로 분리하면 평가가 메인 API 응답을 막지 않는다.

실행:

    poetry run python -m hwarang_api.workers.lora_evaluator_worker

systemd / pm2 등에서 supervisor 로 띄우는 것을 권장.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from hwarang_api.db import connect_db, disconnect_db, prisma
from hwarang_api.grid.code_round.code_round_quality import validate_completed_round

logger = logging.getLogger(__name__)


POLL_INTERVAL_SEC = int(os.getenv("HWARANG_EVAL_WORKER_POLL_SEC", "30"))
GRACE_MINUTES = int(os.getenv("HWARANG_EVAL_WORKER_GRACE_MIN", "2"))
ERROR_BACKOFF_SEC = int(os.getenv("HWARANG_EVAL_WORKER_BACKOFF_SEC", "60"))
DOMAINS = ("code", "design")


def _is_db_ready() -> bool:
    return getattr(prisma, "is_connected", lambda: False)()


async def _fetch_pending_round():
    """평가 대기중인 라운드 1개. 없으면 None."""
    if not _is_db_ready():
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=GRACE_MINUTES)
    for domain in DOMAINS:
        try:
            pending = await prisma.round.find_many(
                where={
                    "domain": domain,
                    "status": "COMPLETED",
                    "qualityScore": None,
                    "completedAt": {"lt": cutoff},
                },
                take=1,
                order={"completedAt": "asc"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Round.find_many(%s) 실패: %s", domain, exc)
            continue
        if pending:
            return pending[0]
    return None


async def worker_loop() -> None:
    """무한 루프 — pending 검증 라운드 처리."""
    await connect_db()
    logger.info(
        "lora_evaluator_worker 시작 (poll=%ds, grace=%dmin)",
        POLL_INTERVAL_SEC,
        GRACE_MINUTES,
    )
    try:
        while True:
            try:
                round_ = await _fetch_pending_round()
                if round_ is None:
                    await asyncio.sleep(POLL_INTERVAL_SEC)
                    continue

                round_id = getattr(round_, "id", None)
                if not round_id:
                    await asyncio.sleep(POLL_INTERVAL_SEC)
                    continue

                logger.info("평가 시작: round %s", round_id)
                try:
                    result = await validate_completed_round(round_id)
                    logger.info("평가 완료: round %s → %s", round_id, result)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("validate_completed_round 실패 (%s): %s", round_id, exc)
                    # 다음 폴링 때 다시 시도되지 않도록 작은 backoff
                    await asyncio.sleep(ERROR_BACKOFF_SEC)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception("평가 워커 메인 루프 에러: %s", exc)
                await asyncio.sleep(ERROR_BACKOFF_SEC)
    finally:
        await disconnect_db()


def main() -> None:
    logging.basicConfig(
        level=os.getenv("HWARANG_LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        asyncio.run(worker_loop())
    except KeyboardInterrupt:
        logger.info("lora_evaluator_worker 종료 (SIGINT)")


if __name__ == "__main__":
    main()
