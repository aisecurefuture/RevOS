"""Listing Video Studio Celery tasks.

Same two-queue split as Pitch Video Studio — no new worker images:

  * ``listing_video.generate_audio`` — routed to the ``avatar`` queue (the
    image with the XTTS venv). Imports no ML libraries directly.
  * ``listing_video.render`` — routed to the ``pitch_video`` queue (the
    Node + Remotion + Chromium image, which also carries the licensed music
    beds under LISTING_VIDEO_MUSIC_DIR). Shells out via subprocess.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.listing_video import ListingVideoJob
from app.workers.celery_app import celery_app

logger = logging.getLogger("revos.listing_video.worker")


async def _run_stage(job_id: str, stage) -> dict:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            job = await session.get(ListingVideoJob, uuid.UUID(job_id))
            if job is None:
                return {"status": "missing"}
            await stage(session, job)
            await session.commit()
            return {"status": str(job.status)}
    finally:
        await engine.dispose()


@celery_app.task(name="listing_video.generate_audio", acks_late=True)
def generate_audio(job_id: str) -> dict:
    """Stage 1: narration audio + photo frame timeline."""
    from app.services import listing_video_service

    return asyncio.run(_run_stage(job_id, listing_video_service.run_audio_generation))


@celery_app.task(name="listing_video.render", acks_late=True)
def render(job_id: str) -> dict:
    """Stage 2: the Remotion MP4 render (ListingVideo composition)."""
    from app.services import listing_video_service

    return asyncio.run(_run_stage(job_id, listing_video_service.run_render))
