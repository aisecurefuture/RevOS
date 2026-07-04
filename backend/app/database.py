"""Database engine and session management.

The API uses an async engine (asyncpg). A sync engine is exposed separately
for Celery tasks and Alembic, which run outside the async request loop.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, create_engine

from app.config import settings
from app.core import (
    tenancy as _tenancy,  # noqa: F401 — registers the tenant write-stamp event
)

# --- Async (request path) ---------------------------------------------------
async_engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,   # recycle dead connections gracefully
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# --- Sync (Celery / scripts) ------------------------------------------------
sync_engine = create_engine(
    settings.sync_database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

SyncSessionLocal = sessionmaker(bind=sync_engine, class_=Session, expire_on_commit=False)


def get_sync_session() -> Session:
    """Return a sync session for use inside Celery tasks / seed scripts."""
    return SyncSessionLocal()
