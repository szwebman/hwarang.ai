"""Database session management."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hwarang_api.config import Settings


def create_engine(settings: Settings):
    """Create async SQLAlchemy engine."""
    return create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_size=10,
        max_overflow=20,
    )


def create_session_factory(settings: Settings) -> async_sessionmaker[AsyncSession]:
    """Create async session factory."""
    engine = create_engine(settings)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
