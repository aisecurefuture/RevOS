"""Lead schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.crm import ContactChannel


class ConsentMode(StrEnum):
    """How a manual opt-in attestation resolves the lead's mailable state."""

    express = "express"            # express written/verbal consent → confirmed (mailable now)
    double_optin = "double_optin"  # send a confirmation email → mailable only after they click


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    email: str
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    company_name: str | None = None
    source: str | None = None
    consent_status: str
    lead_score: int
    confirmed_at: datetime | None = None
    created_at: datetime


class LeadDetailOut(LeadOut):
    tags: list[str] = []


class TagApply(BaseModel):
    tags: list[str] = Field(min_length=1)


class LeadManualCreate(BaseModel):
    """Manually add a lead (and optionally a linked CRM contact) with a
    human attestation that the person opted in. The attestation is captured
    as an immutable ConsentRecord — this is the legal basis for mailing them.
    """

    brand_id: uuid.UUID | None = None       # None → resolved to the account's first brand
    email: EmailStr                          # the primary email — drives the mailable Lead
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)    # primary phone
    company_name: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)   # used only for the linked contact
    source: str | None = Field(default="manual", max_length=120)
    tags: list[str] = Field(default_factory=list)

    # Rich contact detail (stored on the linked Contact when also_create_contact).
    additional_emails: list[ContactChannel] = Field(default_factory=list)
    additional_phones: list[ContactChannel] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=5000)
    address_line1: str | None = Field(default=None, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=30)
    country: str | None = Field(default=None, max_length=80)

    # --- Opt-in attestation (required) ---
    opt_in_attested: bool = False
    consent_basis: str = Field(
        min_length=3, max_length=500,
        description="How consent was obtained, e.g. 'Verbal at open house 2026-07-20'.",
    )
    consent_mode: ConsentMode = ConsentMode.express

    # Also create a CRM sales contact linked to this lead.
    also_create_contact: bool = False
