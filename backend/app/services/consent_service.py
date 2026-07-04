"""Consent lifecycle: double opt-in, confirmation, unsubscribe, suppression.

This is the compliance core. Marketing email is only ever sent to leads whose
``consent_status`` is ``confirmed``; everything here moves leads through that
lifecycle with an auditable ConsentRecord at each step and signed, expiring
tokens for the confirm/unsubscribe links.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import ComplianceError
from app.core.security import make_signed_token, read_signed_token
from app.core.tenancy import set_active_account
from app.models.base import utcnow
from app.models.campaign import Form, FormSubmission
from app.models.email import EmailCategory, Suppression, SuppressionReason
from app.models.lead import ConsentRecord, ConsentStatus, Lead, UTMCapture
from app.models.offer import Offer
from app.services import lead_service, outbox

_CONFIRM_SALT = "double-optin"
_UNSUB_SALT = "unsubscribe"
_CONFIRM_MAX_AGE = 60 * 60 * 24 * 14          # 14 days
_UNSUB_MAX_AGE = 60 * 60 * 24 * 365 * 2       # 2 years


# --- Tokens & URLs ----------------------------------------------------------
def make_confirm_url(lead_id: uuid.UUID, form_id: uuid.UUID) -> str:
    token = make_signed_token({"lead": str(lead_id), "form": str(form_id)}, salt=_CONFIRM_SALT)
    return f"{settings.public_base_url}/api/public/confirm?token={token}"


def make_unsubscribe_url(lead_id: uuid.UUID) -> str:
    token = make_signed_token({"lead": str(lead_id)}, salt=_UNSUB_SALT)
    return f"{settings.public_base_url}/api/public/unsubscribe?token={token}"


# --- Consent records --------------------------------------------------------
async def record_consent(
    db: AsyncSession,
    lead: Lead,
    *,
    status: ConsentStatus,
    source: str | None,
    ip: str | None,
    ua: str | None,
    evidence: dict | None = None,
    consent_type: str = "marketing_email",
) -> None:
    db.add(ConsentRecord(
        lead_id=lead.id, brand_id=lead.brand_id, consent_type=consent_type,
        status=status, source=source, ip_address=ip, user_agent=ua,
        evidence=evidence or {},
    ))
    await db.flush()


# --- Email content (minimal inline HTML; templatized in Module 7) -----------
def _wrap(body: str, unsubscribe_url: str | None = None) -> str:
    footer = (
        f'<p style="font-size:12px;color:#888">'
        f'You can <a href="{unsubscribe_url}">unsubscribe</a> at any time.</p>'
        if unsubscribe_url else ""
    )
    return f'<div style="font-family:sans-serif;max-width:560px">{body}{footer}</div>'


async def _queue_double_optin(db: AsyncSession, lead: Lead, form: Form) -> None:
    url = make_confirm_url(lead.id, form.id)
    body = (
        "<h2>Please confirm your subscription</h2>"
        "<p>Click below to confirm you want to hear from us. "
        "If you didn’t request this, you can ignore this email.</p>"
        f'<p><a href="{url}">Confirm my subscription</a></p>'
    )
    await outbox.enqueue_email(
        db, brand_id=lead.brand_id, to_email=lead.email,
        subject="Confirm your subscription", html_body=_wrap(body),
        category=EmailCategory.double_optin, lead_id=lead.id,
    )


async def _queue_welcome_and_magnet(db: AsyncSession, lead: Lead, form: Form) -> None:
    unsub = make_unsubscribe_url(lead.id)
    body = "<h2>You’re in 🎉</h2><p>Thanks for confirming. Welcome aboard!</p>"
    await outbox.enqueue_email(
        db, brand_id=lead.brand_id, to_email=lead.email,
        subject="Welcome!", html_body=_wrap(body, unsub),
        category=EmailCategory.welcome, lead_id=lead.id,
    )
    if form.lead_magnet_offer_id:
        offer = await db.get(Offer, form.lead_magnet_offer_id)
        if offer and (offer.asset_url or offer.external_url):
            link = offer.asset_url or offer.external_url
            magnet = (
                f"<h2>Here’s your {offer.name}</h2>"
                f'<p><a href="{link}">Download it here</a>.</p>'
            )
            await outbox.enqueue_email(
                db, brand_id=lead.brand_id, to_email=lead.email,
                subject=f"Your download: {offer.name}", html_body=_wrap(magnet, unsub),
                category=EmailCategory.lead_magnet, lead_id=lead.id,
            )


# --- Submission orchestration ----------------------------------------------
async def process_submission(
    db: AsyncSession,
    form: Form,
    *,
    email: str,
    first_name: str | None,
    last_name: str | None,
    phone: str | None,
    company_name: str | None,
    consent: bool,
    utm: dict,
    referrer: str | None,
    extra: dict,
    ip: str | None,
    ua: str | None,
) -> dict:
    """Run the full capture flow. Returns a result dict for the public API."""
    if form.consent_required and not consent:
        raise ComplianceError("Consent is required to submit this form.")

    # Suppressed addresses must never be re-subscribed silently.
    if consent and await is_suppressed(db, form.brand_id, email):
        raise ComplianceError("This email address has opted out and cannot be re-added.")

    lead, _ = await lead_service.find_or_create_lead(
        db, brand_id=form.brand_id, email=email, first_name=first_name,
        last_name=last_name, phone=phone, company_name=company_name, source=form.slug,
    )

    requires_confirmation = False
    evidence = {"form": form.slug, "consent_text": form.consent_text, "consent": consent}

    if consent and lead.consent_status != ConsentStatus.confirmed:
        if form.double_optin:
            lead.consent_status = ConsentStatus.pending_double_optin
            lead.double_optin_sent_at = utcnow()
            await record_consent(db, lead, status=ConsentStatus.pending_double_optin,
                                 source=form.slug, ip=ip, ua=ua, evidence=evidence)
            await _queue_double_optin(db, lead, form)
            requires_confirmation = True
        else:
            lead.consent_status = ConsentStatus.confirmed
            lead.consent_at = utcnow()
            lead.confirmed_at = utcnow()
            await record_consent(db, lead, status=ConsentStatus.confirmed,
                                 source=form.slug, ip=ip, ua=ua, evidence=evidence)
            await _queue_welcome_and_magnet(db, lead, form)
            await _enroll_if_configured(db, form, lead.id)

    # Tags + attribution + submission record happen regardless of consent path.
    if form.tags_to_apply:
        await lead_service.apply_tags(db, lead, form.tags_to_apply, form.brand_id)

    db.add(UTMCapture(
        brand_id=form.brand_id, lead_id=lead.id,
        utm_source=utm.get("utm_source"), utm_medium=utm.get("utm_medium"),
        utm_campaign=utm.get("utm_campaign"), utm_term=utm.get("utm_term"),
        utm_content=utm.get("utm_content"), referrer=referrer, ip_address=ip, user_agent=ua,
    ))
    submission = FormSubmission(
        form_id=form.id, brand_id=form.brand_id, lead_id=lead.id,
        data={"email": email, "first_name": first_name, "last_name": last_name,
              "phone": phone, "company_name": company_name, **extra},
        utm=utm, ip_address=ip, user_agent=ua, consent_given=consent, processed=True,
    )
    db.add(submission)
    await db.flush()

    return {
        "status": "ok",
        "requires_confirmation": requires_confirmation,
        "message": form.success_message
        or ("Please check your email to confirm." if requires_confirmation else "Thanks!"),
        "redirect_url": form.redirect_url,
        "lead_id": str(lead.id),
    }


async def confirm_double_optin(db: AsyncSession, token: str) -> Lead:
    data = read_signed_token(token, salt=_CONFIRM_SALT, max_age_seconds=_CONFIRM_MAX_AGE)
    lead = await db.get(Lead, uuid.UUID(data["lead"]))
    if lead is None or lead.deleted_at is not None:
        raise ComplianceError("This confirmation link is no longer valid.")
    set_active_account(lead.account_id)  # bind no-auth writes to the lead's account
    if lead.consent_status != ConsentStatus.confirmed:
        lead.consent_status = ConsentStatus.confirmed
        lead.consent_at = lead.consent_at or utcnow()
        lead.confirmed_at = utcnow()
        lead.double_optin_token = None
        await record_consent(db, lead, status=ConsentStatus.confirmed,
                             source="double_optin_confirm", ip=None, ua=None)
        form = await db.get(Form, uuid.UUID(data["form"])) if data.get("form") else None
        if form is not None:
            await _queue_welcome_and_magnet(db, lead, form)
            await _enroll_if_configured(db, form, lead.id)
        db.add(lead)
        await db.flush()
    return lead


async def _enroll_if_configured(db: AsyncSession, form: Form, lead_id: uuid.UUID) -> None:
    """Enroll a freshly-confirmed lead into the form's sequence, if set.

    Imported lazily to avoid a circular import (sequence_engine imports this
    module's suppression helpers)."""
    from app.services import sequence_engine

    await sequence_engine.enroll_lead_if_configured(db, form, lead_id)


async def unsubscribe(db: AsyncSession, token: str) -> Lead:
    data = read_signed_token(token, salt=_UNSUB_SALT, max_age_seconds=_UNSUB_MAX_AGE)
    lead = await db.get(Lead, uuid.UUID(data["lead"]))
    if lead is None:
        raise ComplianceError("This unsubscribe link is no longer valid.")
    set_active_account(lead.account_id)  # bind no-auth writes to the lead's account
    lead.consent_status = ConsentStatus.unsubscribed
    lead.unsubscribed_at = utcnow()
    await record_consent(db, lead, status=ConsentStatus.unsubscribed,
                         source="unsubscribe_link", ip=None, ua=None)
    await add_suppression(db, lead.brand_id, lead.email, SuppressionReason.unsubscribe)
    db.add(lead)
    await db.flush()
    return lead


# --- Suppression ------------------------------------------------------------
async def is_suppressed(db: AsyncSession, brand_id: uuid.UUID, email: str) -> bool:
    from sqlmodel import or_, select

    email = email.lower().strip()
    result = await db.execute(
        select(Suppression).where(
            Suppression.email == email,
            or_(Suppression.brand_id == brand_id, Suppression.brand_id.is_(None)),
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def add_suppression(
    db: AsyncSession, brand_id: uuid.UUID, email: str, reason: SuppressionReason
) -> None:
    if await is_suppressed(db, brand_id, email):
        return
    db.add(Suppression(brand_id=brand_id, email=email.lower().strip(), reason=reason))
    await db.flush()
