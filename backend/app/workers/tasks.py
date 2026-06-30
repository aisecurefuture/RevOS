"""Celery tasks: dispatch queued emails through Resend.

Module 6 queues transactional emails (double opt-in, welcome, lead magnet) as
``queued`` EmailMessage rows when Resend is live. This periodic task sends them
using the synchronous send path (send-time compliance enforced). In test mode
those rows are ``test`` status and are never picked up here.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select

from app.config import settings
from app.database import get_sync_session
from app.models.email import EmailMessage, EmailStatus
from app.services import consent_service, email_service
from app.workers.celery_app import celery_app

logger = logging.getLogger("revos.worker")

_BATCH = 100


@celery_app.task(name="revos.dispatch_queued_emails")
def dispatch_queued_emails() -> int:
    """Send up to a batch of queued emails. Returns the count processed."""
    session = get_sync_session()
    processed = 0
    try:
        rows = session.execute(
            select(EmailMessage).where(EmailMessage.status == EmailStatus.queued).limit(_BATCH)
        )
        for message in rows.scalars().all():
            unsub = (consent_service.make_unsubscribe_url(message.lead_id)
                     if message.lead_id else None)
            try:
                email_service.send_message_sync(session, message, unsubscribe_url=unsub)
                processed += 1
            except Exception:  # noqa: BLE001 — one bad message must not stop the batch
                logger.exception("Failed to dispatch email %s", message.id)
                message.status = EmailStatus.failed
                session.add(message)
        session.commit()
    finally:
        session.close()
    return processed


async def _run_sequence_tick() -> dict:
    """Run the async sequence engine on a fresh engine bound to this loop."""
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            from app.services import sequence_engine

            stats = await sequence_engine.tick_due(session)
            await session.commit()
            return stats
    finally:
        await engine.dispose()


@celery_app.task(name="revos.tick_sequences")
def tick_sequences() -> dict:
    """Advance all due sequence enrollments (runs on a 5-minute beat)."""
    return asyncio.run(_run_sequence_tick())


async def _run_media_process(asset_id: str, platforms, enhance: bool) -> int:
    import uuid as _uuid

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            from app.services import media_service

            asset = await media_service.get_asset_or_404(session, _uuid.UUID(asset_id))
            variants = await media_service.process_asset(
                session, asset, platforms=platforms or None, enhance=enhance)
            await session.commit()
            return len(variants)
    finally:
        await engine.dispose()


@celery_app.task(name="revos.process_media")
def process_media(asset_id: str, platforms: list | None = None, enhance: bool = False) -> int:
    """Render media renditions off-request (used for large files / video)."""
    return asyncio.run(_run_media_process(asset_id, platforms, enhance))
