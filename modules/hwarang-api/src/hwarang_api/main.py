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

from hwarang_api.config import Settings
from hwarang_api.routers import admin, chat, cluster, grid, health, knowledge, models
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

    # Routers
    app.include_router(health.router, tags=["Health"])
    app.include_router(chat.router, prefix="/v1", tags=["Chat"])
    app.include_router(models.router, prefix="/v1", tags=["Models"])
    app.include_router(admin.router, prefix="/admin", tags=["Admin"])
    app.include_router(cluster.router, prefix="/admin", tags=["Cluster"])
    app.include_router(grid.router, tags=["Grid/HFL"])
    app.include_router(knowledge.router, tags=["Knowledge/HLKM"])

    return app
