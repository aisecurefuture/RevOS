"""Email sending via Resend, with send-time compliance enforcement.

A small provider abstraction keeps the network out of tests: when Resend is not
configured (or test mode is on) a no-network TestProvider records the send and
returns a fake id. Real sends use the official ``resend`` SDK.

**Compliance is enforced at send time** (not just at queue time): suppressed
addresses are never sent to, and bulk categories (campaign/sequence) only go to
leads whose consent is ``confirmed``. This is the last line of defense against
cold spam.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Session, or_, select

from app.config import settings
from app.models.base import utcnow
from app.models.email import EmailCategory, EmailMessage, EmailStatus, Suppression
from app.models.lead import ConsentStatus, Lead

logger = logging.getLogger("revos.email")

# Categories that are marketing (require confirmed consent to send).
_MARKETING = {EmailCategory.campaign, EmailCategory.sequence}
# Categories that carry a List-Unsubscribe header.
_UNSUBSCRIBABLE = {EmailCategory.campaign, EmailCategory.sequence, EmailCategory.welcome}


@dataclass
class ProviderResult:
    id: str
    provider: str


class TestProvider:
    """No-network provider used in test mode / when Resend is unconfigured."""

    name = "test"

    def send(self, payload: dict) -> ProviderResult:
        logger.info("TEST email -> %s | %s", payload.get("to"), payload.get("subject"))
        return ProviderResult(id=f"test_{uuid.uuid4().hex}", provider=self.name)


class ResendProvider:
    """Real provider backed by the official Resend SDK."""

    name = "resend"

    def __init__(self, api_key: str):
        import resend

        resend.api_key = api_key
        self._resend = resend

    def send(self, payload: dict) -> ProviderResult:
        result = self._resend.Emails.send(payload)
        # SDK returns a dict-like with an "id".
        message_id = result["id"] if isinstance(result, dict) else result.id
        return ProviderResult(id=message_id, provider=self.name)


def get_provider():
    """Live Resend provider only when configured AND not in test mode."""
    if settings.email_enabled:
        return ResendProvider(settings.resend_api_key)
    return TestProvider()


# --- Pure helpers (shared by async + sync paths) ----------------------------
def decide_send(
    message: EmailMessage, *, suppressed: bool, lead_confirmed: bool | None
) -> tuple[bool, str | None]:
    if suppressed:
        return False, "suppressed"
    if message.category in _MARKETING and message.lead_id and lead_confirmed is False:
        return False, "unconfirmed_consent"
    return True, None


def build_payload(message: EmailMessage, *, unsubscribe_url: str | None) -> dict:
    sender = (f"{message.from_name} <{message.from_email}>"
              if message.from_name else message.from_email)
    payload: dict = {
        "from": sender,
        "to": [message.to_email],
        "subject": message.subject,
        "html": message.html_body,
    }
    if message.text_body:
        payload["text"] = message.text_body
    if unsubscribe_url and message.category in _UNSUBSCRIBABLE:
        # RFC 8058 one-click unsubscribe.
        payload["headers"] = {
            "List-Unsubscribe": f"<{unsubscribe_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }
    return payload


def _apply_result(message: EmailMessage, *, allowed: bool, reason: str | None,
                  result: ProviderResult | None) -> EmailMessage:
    if not allowed or result is None:
        message.status = EmailStatus.suppressed
        message.error = reason
        return message
    message.status = EmailStatus.sent
    message.provider_message_id = result.id
    message.sent_at = utcnow()
    message.test_mode = result.provider == "test"
    message.error = None
    return message


# --- Async send (used by API routes) ----------------------------------------
async def _async_suppressed(db: AsyncSession, brand_id: uuid.UUID, email: str) -> bool:
    res = await db.execute(
        select(Suppression).where(
            Suppression.email == email.lower().strip(),
            or_(Suppression.brand_id == brand_id, Suppression.brand_id.is_(None)),
        ).limit(1)
    )
    return res.scalar_one_or_none() is not None


async def _async_lead_confirmed(db: AsyncSession, lead_id: uuid.UUID | None) -> bool | None:
    if lead_id is None:
        return None
    lead = await db.get(Lead, lead_id)
    return lead is not None and lead.consent_status == ConsentStatus.confirmed


async def send_message(db: AsyncSession, message: EmailMessage,
                       *, unsubscribe_url: str | None = None) -> EmailMessage:
    suppressed = await _async_suppressed(db, message.brand_id, message.to_email)
    confirmed = await _async_lead_confirmed(db, message.lead_id)
    allowed, reason = decide_send(message, suppressed=suppressed, lead_confirmed=confirmed)
    result = get_provider().send(build_payload(message, unsubscribe_url=unsubscribe_url)) \
        if allowed else None
    _apply_result(message, allowed=allowed, reason=reason, result=result)
    db.add(message)
    await db.flush()
    await db.refresh(message)
    return message


# --- Sync send (used by the Celery dispatcher) ------------------------------
def _sync_suppressed(db: Session, brand_id: uuid.UUID, email: str) -> bool:
    res = db.execute(
        select(Suppression).where(
            Suppression.email == email.lower().strip(),
            or_(Suppression.brand_id == brand_id, Suppression.brand_id.is_(None)),
        ).limit(1)
    )
    return res.scalar_one_or_none() is not None


def _sync_lead_confirmed(db: Session, lead_id: uuid.UUID | None) -> bool | None:
    if lead_id is None:
        return None
    lead = db.get(Lead, lead_id)
    return lead is not None and lead.consent_status == ConsentStatus.confirmed


def send_message_sync(db: Session, message: EmailMessage,
                      *, unsubscribe_url: str | None = None) -> EmailMessage:
    suppressed = _sync_suppressed(db, message.brand_id, message.to_email)
    confirmed = _sync_lead_confirmed(db, message.lead_id)
    allowed, reason = decide_send(message, suppressed=suppressed, lead_confirmed=confirmed)
    result = get_provider().send(build_payload(message, unsubscribe_url=unsubscribe_url)) \
        if allowed else None
    _apply_result(message, allowed=allowed, reason=reason, result=result)
    db.add(message)
    db.flush()
    db.refresh(message)
    return message
