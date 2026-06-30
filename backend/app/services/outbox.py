"""Email outbox: create EmailMessage records to be dispatched by Module 7.

Module 6 (lead capture) needs to *queue* double-opt-in, welcome, lead-magnet,
and internal-notification emails before the Resend service exists. This module
resolves the per-brand sender identity and writes queued EmailMessage rows; the
Resend dispatcher built in Module 7 picks them up and sends them.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.models.email import EmailCategory, EmailMessage, EmailStatus, SenderIdentity


async def resolve_sender(db: AsyncSession, brand_id: uuid.UUID) -> tuple[str, str]:
    """Return (from_email, from_name) for a brand, falling back to defaults."""
    result = await db.execute(
        select(SenderIdentity).where(
            SenderIdentity.brand_id == brand_id,
            SenderIdentity.deleted_at.is_(None),
        ).order_by(SenderIdentity.is_default.desc())
    )
    sender = result.scalars().first()
    if sender:
        return sender.from_email, sender.from_name
    return settings.default_from_email, settings.default_from_name


async def enqueue_email(
    db: AsyncSession,
    *,
    brand_id: uuid.UUID,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
    category: EmailCategory = EmailCategory.transactional,
    lead_id: uuid.UUID | None = None,
) -> EmailMessage:
    """Create a queued EmailMessage. test_mode follows the global setting so
    nothing is actually delivered until Resend is configured (Module 7)."""
    from_email, from_name = await resolve_sender(db, brand_id)
    message = EmailMessage(
        brand_id=brand_id,
        lead_id=lead_id,
        to_email=to_email,
        from_email=from_email,
        from_name=from_name,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        category=category,
        status=EmailStatus.test if settings.email_test_mode else EmailStatus.queued,
        test_mode=settings.email_test_mode,
    )
    db.add(message)
    await db.flush()
    await db.refresh(message)
    return message
