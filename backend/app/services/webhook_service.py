"""Resend (Svix) webhook verification and email-status updates.

Webhooks are signed with the Svix scheme. We verify the HMAC over
``{id}.{timestamp}.{body}`` in constant time and reject stale timestamps
(replay protection) before trusting any status update.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.core.exceptions import AuthError
from app.models.base import utcnow
from app.models.email import EmailMessage, EmailStatus, SuppressionReason
from app.services import consent_service

_TOLERANCE_SECONDS = 5 * 60


def verify_signature(*, svix_id: str, svix_timestamp: str, svix_signature: str, body: bytes) -> bool:
    secret = settings.resend_webhook_secret
    if not secret or not (svix_id and svix_timestamp and svix_signature):
        return False

    # Replay protection.
    try:
        if abs(time.time() - int(svix_timestamp)) > _TOLERANCE_SECONDS:
            return False
    except ValueError:
        return False

    key = secret.split("_", 1)[1] if secret.startswith("whsec_") else secret
    try:
        secret_bytes = base64.b64decode(key)
    except (ValueError, TypeError):
        return False

    signed = f"{svix_id}.{svix_timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(secret_bytes, signed, hashlib.sha256).digest()).decode()
    # Header is a space-separated list of "v1,<sig>" entries.
    for part in svix_signature.split(" "):
        _, _, sig = part.partition(",")
        if sig and hmac.compare_digest(sig, expected):
            return True
    return False


async def handle_event(db: AsyncSession, event: dict) -> bool:
    """Apply a Resend status event to the matching EmailMessage. Returns True
    if a message was updated."""
    event_type = event.get("type", "")
    data = event.get("data", {}) or {}
    email_id = data.get("email_id") or data.get("id")
    if not email_id:
        return False

    result = await db.execute(
        select(EmailMessage).where(EmailMessage.provider_message_id == email_id)
    )
    message = result.scalar_one_or_none()
    if message is None:
        return False

    now = utcnow()
    if event_type == "email.delivered":
        message.status = EmailStatus.delivered
        message.delivered_at = now
    elif event_type == "email.opened":
        message.opened_at = message.opened_at or now
        message.open_count += 1
        if message.status in (EmailStatus.sent, EmailStatus.delivered):
            message.status = EmailStatus.opened
    elif event_type == "email.clicked":
        message.clicked_at = message.clicked_at or now
        message.click_count += 1
        message.status = EmailStatus.clicked
    elif event_type == "email.bounced":
        message.status = EmailStatus.bounced
        await consent_service.add_suppression(
            db, message.brand_id, message.to_email, SuppressionReason.bounce
        )
    elif event_type == "email.complained":
        message.status = EmailStatus.complained
        await consent_service.add_suppression(
            db, message.brand_id, message.to_email, SuppressionReason.complaint
        )
    else:
        return False

    db.add(message)
    await db.flush()
    return True


def parse_signature_headers(headers) -> tuple[str, str, str]:
    """Raise AuthError if the required Svix headers are missing."""
    svix_id = headers.get("svix-id", "")
    svix_timestamp = headers.get("svix-timestamp", "")
    svix_signature = headers.get("svix-signature", "")
    if not (svix_id and svix_timestamp and svix_signature):
        raise AuthError("Missing webhook signature headers.")
    return svix_id, svix_timestamp, svix_signature
