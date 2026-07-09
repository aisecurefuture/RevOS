"""Pitch Video Studio jobs.

One row per generation request: a validated Deck Spec (JSON) + a brand +
a voice source, turned into a narrated MP4. Mirrors AvatarVideoJob's
job-row-polled-by-the-client pattern.

Narration reuses the exact same XTTS-v2 backend Avatar Personas uses
(``services/avatar/inference.py``), but via a built-in STOCK speaker rather
than voice cloning — there's no consented persona to clone for a brand
narrator, so this path never touches PersonaConsent. ``voice_mode`` also
supports ``clone`` for brands that DO want to reuse one of their own
consented PersonaIdentity voices as the narrator.

Rendering happens in a separate ``pitch-video-worker`` image (Node +
Remotion + Chromium) — the main app / avatar-worker never import Remotion.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, TenantModel


class PitchVideoJobStatus(StrEnum):
    queued = "queued"
    generating_audio = "generating_audio"
    rendering = "rendering"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class PitchVideoVoiceMode(StrEnum):
    stock = "stock"    # built-in XTTS speaker, no cloning, no consent surface
    clone = "clone"     # an existing consented PersonaIdentity's voice


class PitchVideoJob(TenantModel, table=True):
    __tablename__ = "pitch_video_jobs"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)

    title: str = Field(max_length=300)
    aspect_ratio: str = Field(default="16:9", max_length=10)

    voice_mode: PitchVideoVoiceMode = Field(sa_type=sa.String(10))
    speaker_name: str | None = Field(default=None, max_length=100)  # voice_mode=stock
    persona_identity_id: uuid.UUID | None = Field(
        default=None, foreign_key="persona_identities.id", index=True,
    )  # voice_mode=clone

    # The validated Deck Spec, stored verbatim for audit/reproducibility.
    deck_spec: dict = Field(sa_type=JSON)
    # Built during the audio stage: [{"scene_id", "audio_path",
    # "duration_seconds", "frame_start", "frame_count"}, ...]. Drives the
    # Remotion render props — no re-measurement happens on the Node side.
    scene_manifest: list = Field(default_factory=list, sa_type=JSON)

    status: PitchVideoJobStatus = Field(
        default=PitchVideoJobStatus.queued, sa_type=sa.String(20), index=True,
    )
    progress_note: str | None = Field(default=None, max_length=300)
    estimated_seconds: int | None = Field(default=None)
    output_path: str | None = Field(default=None, max_length=600)  # storage key of the .mp4
    error: str | None = Field(default=None, sa_type=sa.Text)

    started_at: datetime | None = Field(default=None)
    finished_at: datetime | None = Field(default=None)

    created_by: uuid.UUID = Field(foreign_key="admin_users.id", index=True)
