"""HLKM 백그라운드 잡 스케줄러.

APScheduler 같은 외부 의존성 없이 ``asyncio`` 만으로 구현.

지원하는 잡 유형:
  * 주기 잡 (`_run_job`) : 고정 간격(초) 마다 실행
  * 크론 잡 (`_run_cron_job`) : 매일 특정 시각 (KST) 실행
  * 요일 잡 (`_run_weekly_job`) : 매주 특정 요일/시각 (KST) 실행

각 잡은 개별 예외를 흡수해 루프 자체가 죽지 않도록 한다.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

# KST = UTC+9
KST = timezone(timedelta(hours=9))

JobFn = Callable[[], Awaitable[Any]]


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _now_kst() -> datetime:
    return datetime.now(tz=KST)


def _seconds_until_next(hour: int, minute: int, weekday: int | None = None) -> float:
    """다음 발화 시각까지 남은 초.

    - ``weekday`` (0=월~6=일) 가 주어지면 요일까지 일치해야 함.
    - KST 기준.
    """
    now = _now_kst()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if weekday is None:
        if target <= now:
            target += timedelta(days=1)
    else:
        # 요일 보정
        days_ahead = (weekday - now.weekday()) % 7
        target += timedelta(days=days_ahead)
        if target <= now:
            target += timedelta(days=7)

    return max(1.0, (target - now).total_seconds())


# ---------------------------------------------------------------------------
# 스케줄러
# ---------------------------------------------------------------------------
class HLKMScheduler:
    """HLKM 백그라운드 잡 관리자.

    사용 예::

        sched = get_scheduler()
        await sched.start()
        ...
        await sched.stop()
    """

    def __init__(self) -> None:
        self.tasks: list[asyncio.Task] = []
        self.running: bool = False
        self.last_run: dict[str, datetime] = {}
        self.last_result: dict[str, dict] = {}
        self.last_error: dict[str, str] = {}

    # -- 수명 관리 ----------------------------------------------------------
    async def start(self) -> None:
        """등록된 모든 잡을 백그라운드 태스크로 띄운다. 중복 호출 안전."""
        if self.running:
            logger.info("HLKMScheduler already running")
            return
        self.running = True
        logger.info("HLKMScheduler starting...")

        loop = asyncio.get_running_loop()

        # 잡 정의 (이름, 스케줄 타입, 작업 함수)
        # 지연 임포트로 prisma/의존 모듈 부재 시에도 import 자체는 성공하게 함.
        self.tasks = [
            loop.create_task(
                self._run_cron_job("daily_verify", 3, 0, self._job_daily_verify),
                name="hlkm.daily_verify",
            ),
            loop.create_task(
                self._run_job("hrag_law_sync", 6 * 3600, self._job_hrag_law),
                name="hlkm.hrag_law_sync",
            ),
            loop.create_task(
                self._run_job("hrag_weather_sync", 3600, self._job_hrag_weather),
                name="hlkm.hrag_weather_sync",
            ),
            loop.create_task(
                self._run_job("hrag_news_sync", 1800, self._job_hrag_news),
                name="hlkm.hrag_news_sync",
            ),
            loop.create_task(
                self._run_weekly_job(
                    "halflife_retrain", weekday=6, hour=4, minute=0,
                    job_fn=self._job_halflife_retrain,
                ),
                name="hlkm.halflife_retrain",
            ),
            loop.create_task(
                self._run_cron_job(
                    "next_check_updater", 2, 0, self._job_update_next_check
                ),
                name="hlkm.next_check_updater",
            ),
            loop.create_task(
                self._run_job("aging_detector", 4 * 3600, self._job_detect_aging),
                name="hlkm.aging_detector",
            ),
            loop.create_task(
                self._run_cron_job(
                    "pending_predictions", 1, 0, self._job_update_pending
                ),
                name="hlkm.pending_predictions",
            ),
            loop.create_task(
                self._run_cron_job("gap_scanner", 5, 0, self._job_scan_gaps),
                name="hlkm.gap_scanner",
            ),
        ]
        logger.info("HLKMScheduler: %d jobs scheduled", len(self.tasks))

    async def stop(self) -> None:
        """모든 잡 태스크를 취소하고 정리."""
        if not self.running:
            return
        self.running = False
        logger.info("HLKMScheduler stopping %d task(s)...", len(self.tasks))
        for t in self.tasks:
            t.cancel()
        # 취소 완료 대기
        for t in self.tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self.tasks = []
        logger.info("HLKMScheduler stopped")

    # -- 잡 실행 루프 -------------------------------------------------------
    async def _run_job(
        self, name: str, interval_seconds: int, job_fn: JobFn
    ) -> None:
        """``interval_seconds`` 주기로 ``job_fn`` 을 호출하는 영구 루프."""
        logger.info("job[%s] every %ds", name, interval_seconds)
        # 최초 실행은 살짝 지연시켜 기동 시점 폭주 방지.
        await asyncio.sleep(min(30, interval_seconds))
        while self.running:
            await self._invoke(name, job_fn)
            try:
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                raise

    async def _run_cron_job(
        self, name: str, hour: int, minute: int, job_fn: JobFn
    ) -> None:
        """매일 KST ``hour:minute`` 에 ``job_fn`` 을 호출."""
        logger.info("cron[%s] daily at %02d:%02d KST", name, hour, minute)
        while self.running:
            wait_s = _seconds_until_next(hour, minute)
            try:
                await asyncio.sleep(wait_s)
            except asyncio.CancelledError:
                raise
            if not self.running:
                return
            await self._invoke(name, job_fn)

    async def _run_weekly_job(
        self, name: str, weekday: int, hour: int, minute: int, job_fn: JobFn
    ) -> None:
        """매주 ``weekday``(0=월) ``hour:minute`` KST 에 실행."""
        logger.info(
            "weekly[%s] weekday=%d %02d:%02d KST", name, weekday, hour, minute
        )
        while self.running:
            wait_s = _seconds_until_next(hour, minute, weekday=weekday)
            try:
                await asyncio.sleep(wait_s)
            except asyncio.CancelledError:
                raise
            if not self.running:
                return
            await self._invoke(name, job_fn)

    async def _invoke(self, name: str, job_fn: JobFn) -> None:
        """단일 실행을 감싸는 공통 로직 (로그 + 예외 + 스태츠)."""
        # 설정에서 토글 확인 (이름 → 플래그 매핑). 설정 모듈 부재 시 무시.
        if not await self._is_enabled(name):
            logger.debug("job[%s] disabled by settings", name)
            return

        logger.info("job[%s] run start", name)
        started = datetime.now(tz=timezone.utc)
        try:
            result = await job_fn()
            summary: dict = result if isinstance(result, dict) else {"result": result}
            self.last_run[name] = started
            self.last_result[name] = summary
            self.last_error.pop(name, None)
            logger.info("job[%s] ok: %s", name, summary)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self.last_run[name] = started
            self.last_error[name] = f"{type(exc).__name__}: {exc}"
            logger.exception("job[%s] failed: %s", name, exc)

    async def _is_enabled(self, name: str) -> bool:
        """스케줄러 토글 플래그 조회. 설정 모듈 미가용 시 기본 활성."""
        flag_map = {
            "daily_verify": "daily_verify_enabled",
            "hrag_law_sync": "hrag_law_sync_enabled",
            "hrag_weather_sync": "hrag_weather_sync_enabled",
            "hrag_news_sync": "hrag_news_sync_enabled",
            "halflife_retrain": "halflife_retrain_enabled",
        }
        field = flag_map.get(name)
        if field is None:
            return True
        try:
            from hwarang_api.knowledge.settings import get_settings

            s = await get_settings()
            return bool(getattr(s, field, True))
        except Exception:  # noqa: BLE001
            return True

    # -- 개별 잡 본체 -------------------------------------------------------
    async def _job_daily_verify(self) -> dict:
        from hwarang_api.knowledge import run_daily_verification
        from hwarang_api.knowledge.settings import get_settings

        s = await get_settings()
        return await run_daily_verification(limit=s.max_verifications_per_run)

    async def _job_hrag_law(self) -> dict:
        from hwarang_api.knowledge import sync_from_hrag

        return await sync_from_hrag("law")

    async def _job_hrag_weather(self) -> dict:
        from hwarang_api.knowledge import sync_from_hrag

        return await sync_from_hrag("weather")

    async def _job_hrag_news(self) -> dict:
        from hwarang_api.knowledge import sync_from_hrag

        return await sync_from_hrag("news")

    async def _job_halflife_retrain(self) -> dict:
        from hwarang_api.knowledge.half_life import HalfLifeModel

        model = HalfLifeModel()
        await model.train()
        return {"trained": True}

    async def _job_update_next_check(self) -> dict:
        from hwarang_api.knowledge.half_life import update_all_next_check_times

        count = await update_all_next_check_times()
        return {"updated": count}

    async def _job_detect_aging(self) -> dict:
        from hwarang_api.knowledge.self_verify import detect_aging_facts

        aged = await detect_aging_facts()
        if aged:
            logger.warning("HLKM aging facts detected: %d", len(aged))
        return {"aged_count": len(aged), "sample": aged[:5]}

    async def _job_update_pending(self) -> dict:
        from hwarang_api.knowledge.prediction import update_pending_predictions

        count = await update_pending_predictions()
        return {"updated": count}

    async def _job_scan_gaps(self) -> dict:
        """미해결 지식 공백에 대해 대체 출처 탐색 시도."""
        from hwarang_api.db import prisma
        from hwarang_api.knowledge.self_verify import find_alternative_source
        from hwarang_api.knowledge.types import KnowledgeFact

        try:
            gaps = await prisma.knowledgegap.find_many(
                where={"status": "open"},
                order={"failureCount": "desc"},
                take=20,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("gap scan DB failed: %s", exc)
            return {"scanned": 0, "found": 0}

        found = 0
        for g in gaps:
            stub = KnowledgeFact(
                content=g.topic,
                domain="general",
                valid_from=datetime.now(tz=timezone.utc),
                source="gap_scanner",
                entity=g.topic,
            )
            url = await find_alternative_source(stub)
            if url:
                found += 1
                try:
                    await prisma.knowledgegap.update(
                        where={"id": g.id},
                        data={"status": "searching"},
                    )
                except Exception:  # noqa: BLE001
                    pass
        return {"scanned": len(gaps), "found": found}

    # -- 상태 조회 ----------------------------------------------------------
    def status(self) -> dict:
        """관리자 대시보드용 요약."""
        jobs = []
        for t in self.tasks:
            name = t.get_name().replace("hlkm.", "")
            jobs.append(
                {
                    "name": name,
                    "running": not t.done(),
                    "last_run": self.last_run.get(name).isoformat()
                    if self.last_run.get(name)
                    else None,
                    "last_result": self.last_result.get(name),
                    "last_error": self.last_error.get(name),
                }
            )
        return {
            "running": self.running,
            "job_count": len(self.tasks),
            "jobs": jobs,
        }


# ---------------------------------------------------------------------------
# 글로벌 싱글톤
# ---------------------------------------------------------------------------
scheduler: HLKMScheduler = HLKMScheduler()


def get_scheduler() -> HLKMScheduler:
    """전역 스케줄러 인스턴스 반환."""
    return scheduler


# ---------------------------------------------------------------------------
# FastAPI 연결 가이드 (main.py 에 추가)
# ---------------------------------------------------------------------------
# lifespan() 안에서:
#
#     from hwarang_api.workers.hlkm_scheduler import get_scheduler
#
#     sched = get_scheduler()
#     await sched.start()
#     try:
#         yield
#     finally:
#         await sched.stop()
#
# 또는 app.on_event("startup")/("shutdown") 훅을 쓰는 레거시 방식:
#
#     @app.on_event("startup")
#     async def _hlkm_start():
#         await get_scheduler().start()
#
#     @app.on_event("shutdown")
#     async def _hlkm_stop():
#         await get_scheduler().stop()
