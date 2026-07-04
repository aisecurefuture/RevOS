"""Bulk campaign email: approval-first preparation, preview, and execution.

Preparing a send selects only **confirmed, non-suppressed** leads (no cold
spam), renders a personalized message per recipient in ``pending_approval``
status, and raises an ApprovalRequest. Nothing is sent until a human approves;
execution then dispatches each message through the send-time-enforced sender.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import or_, select

from app.config import settings
from app.core.exceptions import RevOSError
from app.models.approval import ApprovalAction
from app.models.brand import Brand
from app.models.campaign import Campaign
from app.models.email import EmailCategory, EmailMessage, EmailStatus, Suppression
from app.models.lead import ConsentStatus, Lead, LeadTagLink, Tag
from app.services import (
    approval_service,
    consent_service,
    email_service,
    outbox,
    template_service,
)

# Hard cap to avoid accidental mega-sends; surfaced in logs/approval notes.
_MAX_RECIPIENTS = 5000


async def _recipients(db: AsyncSession, brand_id: uuid.UUID, tag: str | None) -> list[Lead]:
    suppressed = select(Suppression.email).where(
        or_(Suppression.brand_id == brand_id, Suppression.brand_id.is_(None))
    )
    stmt = select(Lead).where(
        Lead.brand_id == brand_id,
        Lead.consent_status == ConsentStatus.confirmed,
        Lead.deleted_at.is_(None),
        Lead.email.notin_(suppressed),
    )
    if tag:
        stmt = stmt.join(LeadTagLink, LeadTagLink.lead_id == Lead.id).join(
            Tag, Tag.id == LeadTagLink.tag_id
        ).where(Tag.name == tag, Tag.brand_id == brand_id)
    stmt = stmt.limit(_MAX_RECIPIENTS)
    return list((await db.execute(stmt)).scalars().all())


def _render(html: str, lead: Lead, brand: Brand, unsubscribe_url: str) -> str:
    rendered = template_service.render_string(html, {
        "first_name": lead.first_name or "there",
        "last_name": lead.last_name or "",
        "email": lead.email,
        "brand_name": brand.name,
        "unsubscribe_url": unsubscribe_url,
    })
    if "unsubscribe" not in rendered.lower():
        rendered += (
            f'<p style="font-size:12px;color:#888;margin-top:24px">'
            f'<a href="{unsubscribe_url}">Unsubscribe</a></p>'
        )
    return rendered


async def prepare_send(
    db: AsyncSession,
    campaign: Campaign,
    *,
    subject: str,
    html_body: str,
    text_body: str | None,
    tag: str | None,
    requested_by: uuid.UUID,
) -> dict:
    brand = await db.get(Brand, campaign.brand_id)
    leads = await _recipients(db, campaign.brand_id, tag)
    if not leads:
        raise RevOSError("No confirmed, mailable recipients match this campaign.")

    from_email, from_name = await outbox.resolve_sender(db, campaign.brand_id)
    for lead in leads:
        unsub = consent_service.make_unsubscribe_url(lead.id)
        db.add(EmailMessage(
            brand_id=campaign.brand_id, lead_id=lead.id, campaign_id=campaign.id,
            to_email=lead.email, from_email=from_email, from_name=from_name,
            subject=subject, html_body=_render(html_body, lead, brand, unsub),
            text_body=text_body, category=EmailCategory.campaign,
            status=EmailStatus.pending_approval,
        ))
    await db.flush()

    approval = await approval_service.create_approval(
        db, action_type=ApprovalAction.campaign_send, brand_id=campaign.brand_id,
        title=f"Send campaign “{campaign.name}” to {len(leads)} recipients",
        entity_type="campaign", entity_id=campaign.id,
        summary=f"Subject: {subject}",
        risk_notes=(f"{len(leads)} confirmed, non-suppressed recipients. "
                    f"Test mode: {settings.email_test_mode}."),
        payload={"campaign_id": str(campaign.id), "recipient_count": len(leads),
                 "subject": subject},
        requested_by=requested_by,
    )
    sample = _render(html_body, leads[0], brand, consent_service.make_unsubscribe_url(leads[0].id))
    return {"approval_id": str(approval.id), "recipient_count": len(leads), "preview_html": sample}


async def execute_send(db: AsyncSession, campaign_id: uuid.UUID) -> int:
    """Send all approved (pending_approval) messages for a campaign. Returns the
    number actually sent (send-time enforcement may still suppress some)."""
    result = await db.execute(
        select(EmailMessage).where(
            EmailMessage.campaign_id == campaign_id,
            EmailMessage.status == EmailStatus.pending_approval,
        )
    )
    messages = list(result.scalars().all())
    sent = 0
    for message in messages:
        unsub = consent_service.make_unsubscribe_url(message.lead_id) if message.lead_id else None
        await email_service.send_message(db, message, unsubscribe_url=unsub)
        if message.status == EmailStatus.sent:
            sent += 1
    return sent


async def cancel_pending(db: AsyncSession, campaign_id: uuid.UUID) -> int:
    result = await db.execute(
        select(EmailMessage).where(
            EmailMessage.campaign_id == campaign_id,
            EmailMessage.status == EmailStatus.pending_approval,
        )
    )
    count = 0
    for message in result.scalars().all():
        message.status = EmailStatus.failed
        message.error = "campaign rejected"
        db.add(message)
        count += 1
    await db.flush()
    return count
