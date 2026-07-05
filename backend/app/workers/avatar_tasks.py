"""Avatar generation Celery task (Phase 3 M3).

Routed to the dedicated ``avatar`` queue (see celery_app task_routes) so only
the avatar-worker — the container that carries the ML stack — ever runs it. The
task body imports no ML libraries directly (the LocalCpuBackend shells out to
isolated venvs), so this module is safe to register in every worker image.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.avatar_job import AvatarVideoJob
from app.workers.celery_app import celery_app


async def _run_avatar_job(job_id: str) -> dict:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            from app.services import avatar_service

            job = await session.get(AvatarVideoJob, uuid.UUID(job_id))
            if job is None:
                return {"status": "missing"}
            await avatar_service.run_generation(session, job)
            await session.commit()
            return {"status": str(job.status)}
    finally:
        await engine.dispose()


@celery_app.task(name="avatar.generate", acks_late=True)
def generate_avatar(job_id: str) -> dict:
    """Generate one avatar video (minutes-to-hours). Long-running; the avatar
    worker should run with a matching visibility timeout."""
    return asyncio.run(_run_avatar_job(job_id))
