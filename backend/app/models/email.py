"""Email: per-brand sender identity, templates, messages, suppression list."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, TenantModel


class EmailCategory(StrEnum):
    transactional = "transactional"
    double_optin = "double_optin"
    welcome = "welcome"
    lead_magnet = "lead_magnet"
    campaign = "campaign"
    sequence = "sequence"
    unsubscribe = "unsubscribe"


class EmailStatus(StrEnum):
    draft = "draft"
    pending_approval = "pending_approval"   # bulk/campaign awaiting human OK
    approved = "approved"
    queued = "queued"
    sending = "sending"
    sent = "sent"
    delivered = "delivered"
    opened = "opened"
    clicked = "clicked"
    bounced = "bounced"
    complained = "complained"
    failed = "failed"
    suppressed = "suppressed"               # blocked by suppression/consent
    test = "test"                           # test-mode, not actually delivered


class SuppressionReason(StrEnum):
    unsubscribe = "unsubscribe"
    bounce = "bounce"
    complaint = "complaint"
    manual = "manual"


class SenderIdentity(TenantModel, table=True):
    """Per-brand verified "from" identity (maps to a Resend verified domain)."""

    __tablename__ = "sender_identities"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    from_name: str = Field(max_length=200)
    from_email: str = Field(max_length=320)
    reply_to: str | None = Field(default=None, max_length=320)
    domain: str | None = Field(default=None, max_length=200)
    is_verified: bool = Field(default=False)
    resend_domain_id: str | None = Field(default=None, max_length=120)
    is_default: bool = Field(default=False)


class EmailTemplate(TenantModel, table=True):
    __tablename__ = "email_templates"

    brand_id: uuid.UUID | None = Field(default=None, foreign_key="brands.id", index=True)
    name: str = Field(max_length=200)
    slug: str = Field(index=True, max_length=160)
    category: EmailCategory = Field(
        default=EmailCategory.campaign, sa_type=sa.String, max_length=20
    )
    subject: str = Field(max_length=400)
    preheader: str | None = Field(default=None, max_length=300)
    html_body: str = Field(sa_type=sa.Text)
    text_body: str | None = Field(default=None, sa_type=sa.Text)
    variables: list = Field(default_factory=list, sa_type=JSON)   # documented merge vars
    is_active: bool = Field(default=True)

    __table_args__ = (sa.UniqueConstraint("brand_id", "slug", name="uq_template_brand_slug"),)


class EmailMessage(TenantModel, table=True):
    """A single rendered email — queued, approved, sent, or suppressed.

    Open/click columns are placeholders populated from Resend webhooks where
    available; they are not inferred via tracking pixels by default.
    """

    __tablename__ = "email_messages"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    lead_id: uuid.UUID | None = Field(default=None, foreign_key="leads.id", index=True)
    contact_id: uuid.UUID | None = Field(default=None, foreign_key="contacts.id", index=True)
    template_id: uuid.UUID | None = Field(default=None, foreign_key="email_templates.id")
    campaign_id: uuid.UUID | None = Field(default=None, foreign_key="campaigns.id", index=True)
    step_run_id: uuid.UUID | None = Field(default=None, foreign_key="step_runs.id", index=True)
    approval_request_id: uuid.UUID | None = Field(
        default=None, foreign_key="approval_requests.id"
    )

    to_email: str = Field(index=True, max_length=320)
    from_email: str = Field(max_length=320)
    from_name: str | None = Field(default=None, max_length=200)
    subject: str = Field(max_length=400)
    html_body: str = Field(sa_type=sa.Text)
    text_body: str | None = Field(default=None, sa_type=sa.Text)
    category: EmailCategory = Field(
        default=EmailCategory.transactional, sa_type=sa.String, max_length=20
    )

    status: EmailStatus = Field(
        default=EmailStatus.draft, sa_type=sa.String, max_length=20, index=True
    )
    test_mode: bool = Field(default=False)
    provider_message_id: str | None = Field(default=None, index=True, max_length=200)
    error: str | None = Field(default=None, sa_type=sa.Text)
    variant_label: str | None = Field(default=None, max_length=40)   # A/B subject variant

    scheduled_at: datetime | None = Field(default=None, index=True)
    sent_at: datetime | None = Field(default=None)
    delivered_at: datetime | None = Field(default=None)
    opened_at: datetime | None = Field(default=None)
    clicked_at: datetime | None = Field(default=None)
    open_count: int = Field(default=0)
    click_count: int = Field(default=0)
    meta: dict = Field(default_factory=dict, sa_type=JSON)


class Suppression(TenantModel, table=True):
    """Do-not-send list. A brand_id of NULL means global suppression."""

    __tablename__ = "suppressions"

    brand_id: uuid.UUID | None = Field(default=None, foreign_key="brands.id", index=True)
    email: str = Field(index=True, max_length=320)
    reason: SuppressionReason = Field(
        default=SuppressionReason.unsubscribe, sa_type=sa.String, max_length=16
    )
    source: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=400)

    __table_args__ = (
        sa.UniqueConstraint("brand_id", "email", name="uq_suppression_brand_email"),
    )
