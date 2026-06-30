"""ApprovalRequest — the generic human-in-the-loop gate.

This is the heart of "approval-first, not blind automation." Any sensitive
action (bulk/campaign send, sequence activation, content/social publish, or an
AI-suggested change) creates an ApprovalRequest that a human must approve before
a worker is allowed to execute it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, BaseModel


class ApprovalAction(StrEnum):
    bulk_email_send = "bulk_email_send"
    campaign_send = "campaign_send"
    sequence_activation = "sequence_activation"
    sequence_step_send = "sequence_step_send"
    content_publish = "content_publish"
    social_publish = "social_publish"
    ai_apply = "ai_apply"                       # apply an AI-generated change
    lead_import = "lead_import"


class ApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"
    expired = "expired"


class ApprovalRequest(BaseModel, table=True):
    __tablename__ = "approval_requests"

    brand_id: uuid.UUID | None = Field(default=None, foreign_key="brands.id", index=True)
    action_type: ApprovalAction = Field(sa_type=sa.String, max_length=30, index=True)
    status: ApprovalStatus = Field(
        default=ApprovalStatus.pending, sa_type=sa.String, max_length=16, index=True
    )
    # What the action targets (e.g. campaign id, sequence id).
    entity_type: str | None = Field(default=None, max_length=60)
    entity_id: uuid.UUID | None = Field(default=None, index=True)

    title: str = Field(max_length=300)
    summary: str | None = Field(default=None, sa_type=sa.Text)
    # Risk/compliance notes surfaced to the reviewer (e.g. recipient count,
    # suppression hits, consent status breakdown).
    risk_notes: str | None = Field(default=None, sa_type=sa.Text)
    # Snapshot of exactly what will execute on approval (recipients, payload).
    payload: dict = Field(default_factory=dict, sa_type=JSON)

    requested_by_user_id: uuid.UUID | None = Field(
        default=None, foreign_key="admin_users.id", index=True
    )
    reviewed_by_user_id: uuid.UUID | None = Field(default=None, foreign_key="admin_users.id")
    decision_reason: str | None = Field(default=None, max_length=500)
    reviewed_at: datetime | None = Field(default=None)
    expires_at: datetime | None = Field(default=None)
