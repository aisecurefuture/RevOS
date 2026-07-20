"""Listing Video Studio schemas.

ListingDetails is the agent's input form — address + facts + selling points.
The voiceover script is drafted deterministically from these fields
(``listing_video_service.draft_script``), then reviewed/edited by the agent,
and finally re-screened by the Fair Housing guard at job creation.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ListingDetails(BaseModel):
    """The input form. Only the address is truly required — everything else
    degrades gracefully in both the drafted script and the overlays."""

    street: str = Field(min_length=3, max_length=150)
    city: str = Field(min_length=2, max_length=100)
    state: str = Field(min_length=2, max_length=50)
    zip_code: str = Field(default="", max_length=20)

    beds: float | None = Field(default=None, ge=0, le=50)
    baths: float | None = Field(default=None, ge=0, le=50)
    sqft: int | None = Field(default=None, ge=0, le=1_000_000)
    lot: str = Field(default="", max_length=100)          # e.g. "0.4 acre lot"
    year_built: int | None = Field(default=None, ge=1600, le=2100)
    price_text: str = Field(default="", max_length=60)    # e.g. "$489,000" — display string, agent-controlled
    listing_type: str = Field(default="For Sale", max_length=40)  # For Sale / For Rent / Open House / Just Listed / Sold

    # Selling points shown as overlay chips + woven into the script,
    # e.g. ["Chef's kitchen", "Lake Michigan views", "3-car garage"].
    features: list[str] = Field(default_factory=list, max_length=10)
    # One free-text hook sentence the agent wants up front (optional).
    hook: str = Field(default="", max_length=300)

    agent_name: str = Field(default="", max_length=120)
    agent_phone: str = Field(default="", max_length=40)
    brokerage: str = Field(default="", max_length=150)

    @field_validator("features")
    @classmethod
    def _trim_features(cls, v: list[str]) -> list[str]:
        cleaned = [f.strip() for f in v if f and f.strip()]
        for f in cleaned:
            if len(f) > 80:
                raise ValueError("Each feature must be 80 characters or fewer.")
        return cleaned

    @property
    def address_line(self) -> str:
        parts = [self.street, self.city, self.state]
        line = ", ".join(p for p in parts if p)
        return f"{line} {self.zip_code}".strip()


class DraftScriptRequest(BaseModel):
    details: ListingDetails


class DraftScriptOut(BaseModel):
    script: str
    # Fair Housing phrases found in the DRAFT inputs (agent-typed hook or
    # features can trip these) — surfaced as warnings at draft time so the
    # agent fixes them before submission, where they become a hard reject.
    fair_housing_flags: list[str]
    estimated_spoken_seconds: int


class PersonaVoiceOut(BaseModel):
    id: uuid.UUID
    name: str


class VoicesOut(BaseModel):
    stock: list[str]
    personas: list[PersonaVoiceOut]


class ListingVideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    address: str
    status: str
    music_track: str
    voice_mode: str
    speaker_name: str
    script: str
    progress_note: str | None
    estimated_seconds: int | None
    error: str | None
    photo_count: int = 0
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    has_output: bool = False

    @classmethod
    def from_job(cls, job) -> "ListingVideoOut":
        out = cls.model_validate(job)
        out.has_output = bool(job.output_path)
        out.photo_count = len(job.photo_paths or [])
        return out


class MusicTracksOut(BaseModel):
    tracks: list[str]
