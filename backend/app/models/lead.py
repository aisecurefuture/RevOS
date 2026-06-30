"""Leads, consent, tags, segments, UTM capture.

A **Lead** is a marketing-list identity governed by consent. It is distinct
from a CRM **Contact** (sales identity) but can be linked to one. Marketing
email is only permitted when `consent_status == confirmed`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, BaseModel


class ConsentStatus(StrEnum):
    none = "none"                       # imported/unknown — NOT mailable
    single_optin = "single_optin"       # opted in, no confirmation step
    pending_double_optin = "pending_double_optin"
    confirmed = "confirmed"             # double opt-in confirmed — mailable
    unsubscribed = "unsubscribed"       # opted out — suppressed


class Lead(BaseModel, table=True):
    __tablename__ = "leads"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    email: str = Field(index=True, max_length=320)
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    company_name: str | None = Field(default=None, max_length=200)

    source: str | None = Field(default=None, index=True, max_length=120)   # form/import/api
    referral_source: str | None = Field(default=None, max_length=300)

    # Consent lifecycle (the compliance backbone).
    consent_status: ConsentStatus = Field(
        default=ConsentStatus.none, sa_type=sa.String, max_length=30, index=True
    )
    consent_at: datetime | None = Field(default=None)
    double_optin_token: str | None = Field(default=None, index=True, max_length=128)
    double_optin_sent_at: datetime | None = Field(default=None)
    confirmed_at: datetime | None = Field(default=None)
    unsubscribed_at: datetime | None = Field(default=None)

    lead_score: int = Field(default=0, index=True)
    interested_offer_id: uuid.UUID | None = Field(default=None, foreign_key="offers.id")
    contact_id: uuid.UUID | None = Field(default=None, foreign_key="contacts.id", index=True)
    custom_fields: dict = Field(default_factory=dict, sa_type=JSON)

    __table_args__ = (
        sa.UniqueConstraint("brand_id", "email", name="uq_lead_brand_email"),
    )

    @property
    def is_mailable(self) -> bool:
        """Marketing email is only allowed for confirmed, non-deleted leads."""
        return self.consent_status == ConsentStatus.confirmed and self.deleted_at is None


class ConsentRecord(BaseModel, table=True):
    """Immutable evidence trail of every consent event (GDPR/CAN-SPAM)."""

    __tablename__ = "consent_records"

    lead_id: uuid.UUID = Field(foreign_key="leads.id", index=True)
    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    consent_type: str = Field(default="marketing_email", max_length=80)
    status: ConsentStatus = Field(sa_type=sa.String, max_length=30)
    source: str | None = Field(default=None, max_length=200)        # form slug / import
    ip_address: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=400)
    evidence: dict = Field(default_factory=dict, sa_type=JSON)       # snapshot of form/consent text


class Tag(BaseModel, table=True):
    __tablename__ = "tags"

    brand_id: uuid.UUID | None = Field(default=None, foreign_key="brands.id", index=True)
    name: str = Field(index=True, max_length=80)
    color: str | None = Field(default=None, max_length=16)

    __table_args__ = (sa.UniqueConstraint("brand_id", "name", name="uq_tag_brand_name"),)


class LeadTagLink(BaseModel, table=True):
    """Many-to-many link between leads and tags."""

    __tablename__ = "lead_tags"

    lead_id: uuid.UUID = Field(foreign_key="leads.id", index=True)
    tag_id: uuid.UUID = Field(foreign_key="tags.id", index=True)

    __table_args__ = (sa.UniqueConstraint("lead_id", "tag_id", name="uq_lead_tag"),)


class Segment(BaseModel, table=True):
    """Saved audience filter; dynamic segments evaluate `rules` at send time."""

    __tablename__ = "segments"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    name: str = Field(max_length=200)
    description: str | None = Field(default=None, sa_type=sa.Text)
    rules: dict = Field(default_factory=dict, sa_type=JSON)
    is_dynamic: bool = Field(default=True)


class UTMCapture(BaseModel, table=True):
    """First-party UTM + referrer capture for attribution."""

    __tablename__ = "utm_captures"

    brand_id: uuid.UUID | None = Field(default=None, foreign_key="brands.id", index=True)
    lead_id: uuid.UUID | None = Field(default=None, foreign_key="leads.id", index=True)
    form_submission_id: uuid.UUID | None = Field(default=None, foreign_key="form_submissions.id")
    utm_source: str | None = Field(default=None, max_length=200, index=True)
    utm_medium: str | None = Field(default=None, max_length=200)
    utm_campaign: str | None = Field(default=None, max_length=200, index=True)
    utm_term: str | None = Field(default=None, max_length=200)
    utm_content: str | None = Field(default=None, max_length=200)
    landing_path: str | None = Field(default=None, max_length=500)
    referrer: str | None = Field(default=None, max_length=500)
    ip_address: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=400)
