"""FastAPI application factory.

Supports two modes:
- Local mode (default): Model loaded in the API server process
- Distributed mode (HWARANG_DISTRIBUTED=true): Delegates to Worker nodes via Redis
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from hwarang_api.config import Settings
from hwarang_api.grid.sharder import SHARD_DIR
from hwarang_api.routers import (
    active_inference,
    admin,
    audio,
    chat,
    cluster,
    cognitive,
    coin,
    crawl,
    grid,
    health,
    hwarang_protocol,
    knowledge,
    learning,
    models,
    options,
    realtime,
    research,
    scheduler,
    self_modify,
    self_play,
    sleep,
    social,
    trust,
    trusted_sources,
    vision,
)
from hwarang_api.services.model_manager import ModelManager

logger = logging.getLogger(__name__)

# Global model manager
model_manager = ModelManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    settings: Settings = app.state.settings

    # HLKM 스케줄러 + Prisma 연결
    from hwarang_api.db import prisma as hlkm_prisma, connect_db, disconnect_db
    from hwarang_api.workers.hlkm_scheduler import get_scheduler

    hlkm_scheduler = get_scheduler()
    try:
        await connect_db()
        await hlkm_scheduler.start()
        logger.info("HLKM scheduler started, Prisma connected")
    except Exception as e:
        logger.warning(f"HLKM 초기화 실패(계속 진행): {e}")

    # Online RLHF 워커 — 매 피드백마다 즉시 1 step gradient
    try:
        from hwarang_api.learning.online.continuous_lora import init_worker as _online_init

        await _online_init()
    except Exception as e:
        logger.warning(f"Online LoRA worker 초기화 실패(계속 진행): {e}")

    if settings.distributed:
        # ===== Distributed mode: connect to Redis, workers handle models =====
        logger.info("Starting in DISTRIBUTED mode")
        from hwarang_api.distributed.load_balancer import LoadBalancer

        lb = LoadBalancer(redis_url=settings.redis_url)
        await lb.connect()
        app.state.load_balancer = lb

        workers = await lb.get_workers()
        logger.info(f"Connected to cluster: {len(workers)} worker(s) online")

        yield

        await lb.close()
        logger.info("LoadBalancer disconnected")

    else:
        # ===== Local mode: load model in-process =====
        logger.info("Starting in LOCAL mode (single server)")
        try:
            logger.info(f"Loading default model: {settings.default_model}")
            await model_manager.load_model(
                model_id=settings.default_model,
                model_path=settings.model_path,
                device=settings.device,
                dtype=settings.dtype,
            )
            logger.info("Default model loaded successfully")
        except Exception as e:
            logger.warning(f"Could not load default model: {e}. Server starting without models.")

        yield

        logger.info("Shutting down, unloading models...")
        await model_manager.unload_all()

    # HLKM 스케줄러 + Prisma 종료
    try:
        await hlkm_scheduler.stop()
        await disconnect_db()
        logger.info("HLKM scheduler stopped, Prisma disconnected")
    except Exception as e:
        logger.warning(f"HLKM 종료 중 오류: {e}")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if settings is None:
        settings = Settings()

    mode = "distributed" if settings.distributed else "local"
    app = FastAPI(
        title="Hwarang API",
        description=f"OpenAI-compatible API for Hwarang LLM (mode: {mode})",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.model_manager = model_manager
    app.state.load_balancer = None  # Set during lifespan if distributed

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 정적 파일: 라운드 샤드 파일 서빙 (/static/shards/{round_id}/shard_*.jsonl)
    try:
        SHARD_DIR.mkdir(parents=True, exist_ok=True)
        app.mount(
            "/static/shards",
            StaticFiles(directory=str(SHARD_DIR)),
            name="shards",
        )
    except Exception as e:
        logger.warning(f"샤드 정적 파일 마운트 실패(계속): {e}")

    # Routers
    app.include_router(health.router, tags=["Health"])
    app.include_router(chat.router, prefix="/v1", tags=["Chat"])
    app.include_router(models.router, prefix="/v1", tags=["Models"])
    # Hwarang Protocol (HP) v1.0 — DSL/Markup/Workflow 전용 엔드포인트
    # prefix=/v1/hwarang 는 라우터 자체에 정의됨
    app.include_router(hwarang_protocol.router)
    app.include_router(admin.router, prefix="/admin", tags=["Admin"])
    app.include_router(cluster.router, prefix="/admin", tags=["Cluster"])
    app.include_router(grid.router, tags=["Grid/HFL"])
    app.include_router(coin.router, tags=["Coin/Emission"])
    app.include_router(knowledge.router, tags=["Knowledge/HLKM"])
    app.include_router(learning.router, tags=["Learning/HSEE"])
    app.include_router(trusted_sources.router, tags=["TrustedSources"])
    app.include_router(crawl.router, tags=["DistributedCrawl"])
    app.include_router(research.router, tags=["Research"])
    app.include_router(research.feedback_router, tags=["CodeFeedback"])
    app.include_router(realtime.router, tags=["Realtime"])
    app.include_router(vision.router, tags=["Vision/VLM"])
    app.include_router(audio.router, tags=["Audio/STT"])
    app.include_router(options.router, tags=["Options"])
    app.include_router(cognitive.router, tags=["Cognitive"])
    app.include_router(self_modify.router, tags=["SelfModify"])
    app.include_router(social.router, tags=["Social"])
    # Unified Trust facade — Agent/Source 평판 통합 조회 (저장은 각 도메인 그대로)
    app.include_router(trust.router, tags=["Trust"])
    # Active Inference (Phase 9.η) — prefix 는 라우터 자체에 정의됨
    app.include_router(active_inference.router, tags=["ActiveInference"])
    # Adversarial Self-Play (Phase 9.θ) — prefix /api/self-play 는 라우터 자체에 정의됨
    app.include_router(self_play.router, tags=["SelfPlay"])
    # Sleep Cycle / Memory Consolidation (Phase 9.ι) — prefix /api/sleep 는 라우터 자체에 정의됨
    app.include_router(sleep.router, tags=["Sleep"])
    # Scheduler 관리 (분산 락/잡 상태) — prefix /api/scheduler 는 라우터 자체에 정의됨
    app.include_router(scheduler.router, tags=["Scheduler"])

    return app
