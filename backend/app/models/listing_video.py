"""Listing Video Studio jobs (real estate).

One row per generation request: an agent's listing details + ordered photos,
turned into a ~30s vertical (9:16) social video — Ken Burns slideshow with
address/price/feature overlays, an XTTS stock-voice narration, and an
optional licensed music bed.

Mirrors PitchVideoJob's job-row-polled-by-the-client pattern and reuses the
exact same two workers: the audio stage runs on the avatar queue (XTTS venv),
the render stage on the pitch_video queue (Node + Remotion + Chromium). No
new worker images.

The voiceover script is ALWAYS reviewed by the agent before a job is created
(the API drafts it, the human edits/approves it), and it is re-screened at
creation time against the Fair Housing guard in listing_video_service — any
steering/demographic language rejects the job with the flagged phrases.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, TenantModel


class ListingVideoJobStatus(StrEnum):
    queued = "queued"
    generating_audio = "generating_audio"
    rendering = "rendering"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class ListingVideoJob(TenantModel, table=True):
    __tablename__ = "listing_video_jobs"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)

    # Display line, e.g. "412 Sheridan Rd, Winthrop Harbor, IL".
    address: str = Field(max_length=300)
    # The validated ListingDetails payload (beds/baths/sqft/price/features/…),
    # stored verbatim for audit/reproducibility.
    details: dict = Field(sa_type=JSON)
    # The agent-approved narration script actually sent to TTS.
    script: str = Field(sa_type=sa.Text)

    # Ordered storage keys of the uploaded photos (render order).
    photo_paths: list = Field(default_factory=list, sa_type=JSON)
    # Filename of the licensed music bed ("" = no music).
    music_track: str = Field(default="", max_length=200)

    # Narration voice: a built-in XTTS stock speaker, or (voice_mode=clone) an
    # existing CONSENTED PersonaIdentity's voice — same consent surface as
    # Avatar Personas; only status=ready identities are eligible.
    voice_mode: str = Field(default="stock", sa_type=sa.String(10))
    speaker_name: str = Field(default="", max_length=100)  # voice_mode=stock
    persona_identity_id: uuid.UUID | None = Field(
        default=None, foreign_key="persona_identities.id", index=True,
    )  # voice_mode=clone
    # Built during the audio stage: narration duration + per-photo frame
    # timeline. Drives the Remotion render props — no re-measurement on the
    # Node side.
    render_manifest: dict = Field(default_factory=dict, sa_type=JSON)

    status: ListingVideoJobStatus = Field(
        default=ListingVideoJobStatus.queued, sa_type=sa.String(20), index=True,
    )
    progress_note: str | None = Field(default=None, max_length=300)
    estimated_seconds: int | None = Field(default=None)
    output_path: str | None = Field(default=None, max_length=600)  # storage key of the .mp4
    error: str | None = Field(default=None, sa_type=sa.Text)

    started_at: datetime | None = Field(default=None)
    finished_at: datetime | None = Field(default=None)

    created_by: uuid.UUID = Field(foreign_key="admin_users.id", index=True)
