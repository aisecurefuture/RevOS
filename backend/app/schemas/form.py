"""Form schemas (lead-capture form definitions)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.campaign import FormType
from app.schemas.common import HttpUrlStr


class FormField(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=160)
    type: str = Field(default="text", max_length=20)  # text|email|tel|textarea|select
    required: bool = False


class FormCreate(BaseModel):
    brand_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=160)
    form_type: FormType = FormType.newsletter
    fields: list[FormField] = Field(default_factory=list)
    consent_required: bool = True
    consent_text: str | None = None
    double_optin: bool = True
    success_message: str | None = Field(default=None, max_length=500)
    redirect_url: HttpUrlStr | None = Field(default=None, max_length=500)
    tags_to_apply: list[str] = Field(default_factory=list)
    notify_emails: list[EmailStr] = Field(default_factory=list)
    lead_magnet_offer_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None
    enroll_sequence_id: uuid.UUID | None = None
    embed_enabled: bool = True


class FormUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    form_type: FormType | None = None
    fields: list[FormField] | None = None
    consent_required: bool | None = None
    consent_text: str | None = None
    double_optin: bool | None = None
    success_message: str | None = Field(default=None, max_length=500)
    redirect_url: HttpUrlStr | None = Field(default=None, max_length=500)
    tags_to_apply: list[str] | None = None
    notify_emails: list[EmailStr] | None = None
    lead_magnet_offer_id: uuid.UUID | None = None
    enroll_sequence_id: uuid.UUID | None = None
    embed_enabled: bool | None = None
    is_active: bool | None = None


class FormOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    name: str
    slug: str
    form_type: str
    fields: list = []
    consent_required: bool
    consent_text: str | None = None
    double_optin: bool
    success_message: str | None = None
    redirect_url: str | None = None
    tags_to_apply: list = []
    lead_magnet_offer_id: uuid.UUID | None = None
    embed_enabled: bool
    is_active: bool
    created_at: datetime
