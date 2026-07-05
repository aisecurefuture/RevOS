"""Avatar video generation jobs (Phase 3 M3).

One row per generation request. The main app creates the job (status=queued)
and enqueues a Celery task on the dedicated ``avatar`` queue; the separate
avatar-worker (which has the ML stack) processes it, updating status and the
output path on the same row. Generation is minutes-to-hours on CPU, so the row
is the durable source of truth for progress — the client polls it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import TenantModel


class AvatarJobStatus(StrEnum):
    queued = "queued"
    processing = "processing"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class AvatarVideoJob(TenantModel, table=True):
    __tablename__ = "avatar_video_jobs"

    persona_identity_id: uuid.UUID = Field(foreign_key="persona_identities.id", index=True)
    brand_id: uuid.UUID | None = Field(default=None, foreign_key="brands.id", index=True)

    script: str = Field(sa_type=sa.Text)
    target_seconds: int = Field(default=15)   # 7/15/30/45/60/90/120

    status: AvatarJobStatus = Field(
        default=AvatarJobStatus.queued, sa_type=sa.String(16), index=True,
    )
    estimated_seconds: int | None = Field(default=None)  # wait-time estimate at creation
    output_path: str | None = Field(default=None, max_length=600)  # storage key of the .mp4
    error: str | None = Field(default=None, sa_type=sa.Text)

    started_at: datetime | None = Field(default=None)
    finished_at: datetime | None = Field(default=None)

    created_by: uuid.UUID = Field(foreign_key="admin_users.id", index=True)
