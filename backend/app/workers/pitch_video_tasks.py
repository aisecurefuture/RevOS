"""Pitch Video Studio Celery tasks.

Two tasks, two queues, two different worker images:

  * ``pitch_video.generate_audio`` — routed to the ``avatar`` queue (see
    celery_app task_routes), so it only ever runs on the EXISTING
    avatar-worker image (the one with the XTTS venv). Imports no ML libraries
    directly — same safety property as avatar_tasks.py.
  * ``pitch_video.render`` — routed to the ``pitch_video`` queue, so it only
    ever runs on the NEW pitch-video-worker image (Node + Remotion +
    Chromium). Imports nothing Node-specific either — it shells out via
    subprocess, so this module is safe to register in every worker image.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from celery.signals import celeryd_after_setup
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.pitch_video import PitchVideoJob
from app.workers.celery_app import celery_app

logger = logging.getLogger("revos.pitch_video.worker")


@celeryd_after_setup.connect
def _licensing_notice(sender: str, instance, **kwargs) -> None:
    """Standing reminder on every worker that consumes the pitch_video queue.

    Remotion is free for individuals/non-profits/companies with <=3 employees;
    4+ employees require a paid company license (remotion.dev/license).
    Confirmed <=3 employees 2026-07-07 — re-verify if headcount changes.
    """
    queues = {q.name for q in instance.app.amqp.queues.consume_from.values()}
    if "pitch_video" in queues:
        logger.info(
            "Pitch Video Studio renders with Remotion. License status: free tier "
            "(<=3 employees, confirmed 2026-07-07). If the operating company now has "
            "4+ employees, purchase a company license before rendering: "
            "https://www.remotion.dev/license"
        )


async def _run_stage(job_id: str, stage) -> dict:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            job = await session.get(PitchVideoJob, uuid.UUID(job_id))
            if job is None:
                return {"status": "missing"}
            await stage(session, job)
            await session.commit()
            return {"status": str(job.status)}
    finally:
        await engine.dispose()


@celery_app.task(name="pitch_video.generate_audio", acks_late=True)
def generate_audio(job_id: str) -> dict:
    """Stage 1: narration audio per scene + duration/frame manifest."""
    from app.services import pitch_video_service

    return asyncio.run(_run_stage(job_id, pitch_video_service.run_audio_generation))


@celery_app.task(name="pitch_video.render", acks_late=True)
def render(job_id: str) -> dict:
    """Stage 2: the actual Remotion MP4 render."""
    from app.services import pitch_video_service

    return asyncio.run(_run_stage(job_id, pitch_video_service.run_render))
