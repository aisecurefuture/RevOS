"""Content autopilot config (Phase 3) — hands-off on-brand content generation.

Per-brand. When ``enabled``, a beat run generates on-brand social captions
(grounded in the brand book), gates each through the brand-book accuracy check,
and either queues it for approval or — when ``auto_publish`` is on and the
content passes cleanly — auto-approves and publishes it. Blocked content is
never posted; merely-flagged content always waits for a human.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, TenantModel


class AutopilotConfig(TenantModel, table=True):
    __tablename__ = "autopilot_configs"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True, unique=True)
    enabled: bool = Field(default=False, index=True)
    # When True, cleanly-passing content is auto-approved and published without a
    # human. Flagged/blocked content is never auto-published regardless.
    auto_publish: bool = Field(default=False)

    platforms: list = Field(default_factory=list, sa_type=JSON)   # e.g. ["facebook","linkedin"]
    posts_per_run: int = Field(default=1)
    run_interval_hours: int = Field(default=24)
    content_themes: list = Field(default_factory=list, sa_type=JSON)  # rotated angles
    default_cta: str | None = Field(default=None, max_length=300)

    last_run_at: datetime | None = Field(default=None)
    configured_by: uuid.UUID | None = Field(default=None, foreign_key="admin_users.id")
