"""Viral video scripts (Phase 3 M4).

A spoken script for a talking-head avatar video: generated grounded in the brand
book, sized to a target duration (words ≈ duration × speaking rate), optimized
for short-form (hook → value → CTA), and run through the brand-book accuracy
gate. Reviewable/editable before it's committed to a (slow) avatar generation
job — so a bad script is caught in seconds, not after an hour of rendering.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, TenantModel


class VideoScript(TenantModel, table=True):
    __tablename__ = "video_scripts"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    persona_identity_id: uuid.UUID | None = Field(
        default=None, foreign_key="persona_identities.id", index=True,
    )

    target_seconds: int = Field(default=15)
    angle: str | None = Field(default=None, max_length=500)  # the seed topic/theme

    script: str = Field(sa_type=sa.Text)
    hook: str | None = Field(default=None, max_length=500)   # the opening line
    word_count: int = Field(default=0)

    # Brand-book accuracy gate result at generation/edit time.
    passed_gate: bool = Field(default=False, index=True)
    gate: dict = Field(default_factory=dict, sa_type=JSON)

    created_by: uuid.UUID = Field(foreign_key="admin_users.id", index=True)
