"""CLI: ``python -m hwarang_api.cognitive.sleep`` — 1 사이클 수동 실행.

운영 환경에서 cron 으로 등록하기 전 디버깅 / 검증용.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from hwarang_api.db import connect_db, disconnect_db

from .sleep_scheduler import SleepScheduler


async def _run(actor: str, top_n: int, seeds: int, variations: int) -> int:
    await connect_db()
    try:
        sched = SleepScheduler(
            actor=actor,
            replay_top_n=top_n,
            dream_seed_count=seeds,
            dream_variations=variations,
        )
        result = await sched.run_sleep_cycle()
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if not result.errors else 1
    finally:
        await disconnect_db()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser(prog="hwarang_api.cognitive.sleep")
    p.add_argument("--actor", default="master")
    p.add_argument("--top-n", type=int, default=50)
    p.add_argument("--seeds", type=int, default=10)
    p.add_argument("--variations", type=int, default=3)
    args = p.parse_args()
    return asyncio.run(
        _run(args.actor, args.top_n, args.seeds, args.variations)
    )


if __name__ == "__main__":
    sys.exit(main())
