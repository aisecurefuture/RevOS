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


async def _run_auto_approvals() -> dict:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            from app.services import automation_service

            stats = await automation_service.run_auto_approvals(session)
            await session.commit()
            return stats
    finally:
        await engine.dispose()


@celery_app.task(name="revos.auto_approve_sweep")
def auto_approve_sweep() -> dict:
    """Every minute: execute pending approvals for accounts in auto-approve mode."""
    return asyncio.run(_run_auto_approvals())


async def _run_scheduled_posts() -> dict:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            from app.services import social_connection_service

            stats = await social_connection_service.publish_scheduled_due(session)
            await session.commit()
            return stats
    finally:
        await engine.dispose()


@celery_app.task(name="revos.publish_scheduled_posts")
def publish_scheduled_posts() -> dict:
    """Every minute: publish approved social posts whose scheduled time arrived."""
    return asyncio.run(_run_scheduled_posts())


async def _run_autopilot() -> dict:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            from app.services import content_autopilot_service

            stats = await content_autopilot_service.run_autopilot(session)
            await session.commit()
            return stats
    finally:
        await engine.dispose()


@celery_app.task(name="revos.content_autopilot")
def content_autopilot() -> dict:
    """Hourly: generate + gate on-brand content for brands whose cadence is due."""
    return asyncio.run(_run_autopilot())


async def _run_expire_trials() -> dict:
    """Find trials that ended in the last hour and send reminder / expiry emails."""
    from datetime import timedelta

    from sqlmodel import select

    from app.models.billing import Subscription, SubscriptionStatus
    from app.models.base import utcnow as _utcnow
    from app.services.transactional_email import send_transactional

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    expired_count = 0
    reminded_count = 0
    try:
        async with factory() as session:
            now = _utcnow()
            # Find subscriptions trialing with trial_ends_at in the past.
            res = await session.execute(
                select(Subscription).where(
                    Subscription.status == SubscriptionStatus.trialing,
                    Subscription.trial_ends_at <= now,
                )
            )
            for sub in res.scalars().all():
                # Already handled — skip.
                if sub.canceled_at is not None:
                    continue
                # Send expiry notification email via the account owner.
                from app.models.account import Account
                from app.models.user import AdminUser

                acct = await session.get(Account, sub.account_id)
                if acct:
                    owner = await session.get(AdminUser, acct.owner_user_id)
                    if owner:
                        try:
                            send_transactional(
                                to_email=owner.email,
                                subject="Your RevOS trial has ended — upgrade to keep access",
                                html=(
                                    f"<p>Hi {owner.full_name or 'there'},</p>"
                                    f"<p>Your 14-day RevOS trial for <strong>{acct.name}</strong> "
                                    f"has ended.</p>"
                                    f"<p>Upgrade to Pro ($149/mo) or Agency ($449/mo) to keep "
                                    f"all your data and continue automating.</p>"
                                    f'<p><a href="{settings.frontend_base_url}/billing">'
                                    f"Upgrade now</a></p>"
                                ),
                            )
                        except Exception:
                            logger.exception("Failed to send trial expiry email to %s", owner.email)
                expired_count += 1
            await session.commit()
    finally:
        await engine.dispose()
    return {"expired": expired_count, "reminded": reminded_count}


@celery_app.task(name="revos.expire_trials")
def expire_trials() -> dict:
    """Hourly: detect expired trials and notify account owners."""
    return asyncio.run(_run_expire_trials())
