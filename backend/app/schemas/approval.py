"""Approval request schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID | None = None
    action_type: str
    status: str
    title: str
    summary: str | None = None
    risk_notes: str | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    payload: dict = {}
    created_at: datetime
    reviewed_at: datetime | None = None


class ApprovalDecision(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class ApprovalResult(BaseModel):
    status: str
    detail: str | None = None
    sent: int | None = None
