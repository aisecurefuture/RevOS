"""Schemas for automation / auto-approve (P3-M7)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AutoApproveRequest(BaseModel):
    enabled: bool
    # Hours to keep auto-approve on. None (with enabled=True) means indefinite,
    # until toggled off. Capped at 90 days.
    duration_hours: int | None = Field(default=None, ge=1, le=24 * 90)


class AutoApproveStatus(BaseModel):
    enabled: bool
    until: datetime | None = None
    indefinite: bool = False
