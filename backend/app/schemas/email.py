"""Email message, template, suppression, preview, and campaign-send schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.email import EmailCategory, SuppressionReason


class EmailMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    to_email: str
    subject: str
    category: str
    status: str
    test_mode: bool
    provider_message_id: str | None = None
    sent_at: datetime | None = None
    opened_at: datetime | None = None
    clicked_at: datetime | None = None
    open_count: int
    click_count: int
    created_at: datetime


class TestSendRequest(BaseModel):
    brand_id: uuid.UUID
    to_email: EmailStr
    subject: str = Field(min_length=1, max_length=400)
    html_body: str = Field(min_length=1)
    text_body: str | None = None


class PreviewRequest(BaseModel):
    subject: str = Field(default="", max_length=400)
    html_body: str = Field(min_length=1)
    context: dict = Field(default_factory=dict)


class PreviewResult(BaseModel):
    subject: str
    html: str


class TemplateCreate(BaseModel):
    brand_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=160)
    category: EmailCategory = EmailCategory.campaign
    subject: str = Field(min_length=1, max_length=400)
    preheader: str | None = Field(default=None, max_length=300)
    html_body: str = Field(min_length=1)
    text_body: str | None = None
    variables: list[str] = Field(default_factory=list)


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: EmailCategory | None = None
    subject: str | None = Field(default=None, min_length=1, max_length=400)
    preheader: str | None = Field(default=None, max_length=300)
    html_body: str | None = None
    text_body: str | None = None
    variables: list[str] | None = None
    is_active: bool | None = None


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID | None = None
    name: str
    slug: str
    category: str
    subject: str
    preheader: str | None = None
    html_body: str
    text_body: str | None = None
    variables: list = []
    is_active: bool
    created_at: datetime


class SuppressionCreate(BaseModel):
    brand_id: uuid.UUID | None = None
    email: EmailStr
    reason: SuppressionReason = SuppressionReason.manual
    note: str | None = Field(default=None, max_length=400)


class SuppressionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID | None = None
    email: str
    reason: str
    created_at: datetime


class CampaignSendPrepare(BaseModel):
    subject: str = Field(min_length=1, max_length=400)
    html_body: str = Field(min_length=1)
    text_body: str | None = None
    tag: str | None = Field(default=None, max_length=80)  # optional segment filter


class CampaignSendResult(BaseModel):
    approval_id: str
    recipient_count: int
    preview_html: str
