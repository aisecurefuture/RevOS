"""Deck Spec + API schemas for Pitch Video Studio.

The Deck Spec is the single source of truth pasted/uploaded by the user — it
carries its own brand slug, title, aspect ratio, and per-scene narration.
Validated once on submit; stored verbatim on the job row for audit/replay.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Scene content — one shape per layout in the scene library
# ---------------------------------------------------------------------------

class HeroContent(BaseModel):
    eyebrow: str | None = None
    headline: str = Field(min_length=1, max_length=300)
    sub: str | None = Field(default=None, max_length=500)


class StatementContent(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    # Optional "A + B = C" style equation rendering (e.g. scene 5's
    # governance + security = trust platform beat). Each term rendered in
    # sequence with "+"/"=" connectors; omit for a plain centered statement.
    equation: list[str] | None = None


class StatItem(BaseModel):
    value: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=200)


class StatTrioContent(BaseModel):
    stats: list[StatItem] = Field(min_length=2, max_length=4)


class TwoColumnPane(BaseModel):
    heading: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=500)


class TwoColumnContent(BaseModel):
    left: TwoColumnPane
    right: TwoColumnPane


class ArchitectureBand(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=300)


class ArchitectureContent(BaseModel):
    bands: list[ArchitectureBand] = Field(min_length=1, max_length=8)


class BarSegment(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    value: float = Field(ge=0)


class Bar(BaseModel):
    category: str = Field(min_length=1, max_length=40)
    segments: list[BarSegment] = Field(min_length=1)


class BarChartContent(BaseModel):
    bars: list[Bar] = Field(min_length=1, max_length=12)
    y_label: str | None = None
    # e.g. "Illustrative model — not a forecast". Rendered on-screen; required
    # whenever the deck shows a financial projection.
    note: str | None = Field(default=None, max_length=200)


class TimelineStep(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=300)


class TimelineContent(BaseModel):
    steps: list[TimelineStep] = Field(min_length=2, max_length=10)


class TeamMember(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    role: str = Field(min_length=1, max_length=200)
    bio: str | None = Field(default=None, max_length=400)


class TeamContent(BaseModel):
    members: list[TeamMember] = Field(min_length=1, max_length=12)


class CloseContent(BaseModel):
    headline: str = Field(min_length=1, max_length=300)
    sub: str | None = Field(default=None, max_length=500)


# ---------------------------------------------------------------------------
# Scene — discriminated union on `layout`
# ---------------------------------------------------------------------------

class _SceneBase(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    variant: Literal["light", "dark"] = "light"
    narration: str = Field(min_length=1, max_length=2000)


class HeroScene(_SceneBase):
    layout: Literal["hero"]
    content: HeroContent


class StatementScene(_SceneBase):
    layout: Literal["statement"]
    content: StatementContent


class StatTrioScene(_SceneBase):
    layout: Literal["stat-trio"]
    content: StatTrioContent


class TwoColumnScene(_SceneBase):
    layout: Literal["two-column"]
    content: TwoColumnContent


class ArchitectureScene(_SceneBase):
    layout: Literal["architecture"]
    content: ArchitectureContent


class BarChartScene(_SceneBase):
    layout: Literal["bar-chart"]
    content: BarChartContent


class TimelineScene(_SceneBase):
    layout: Literal["timeline"]
    content: TimelineContent


class TeamScene(_SceneBase):
    layout: Literal["team"]
    content: TeamContent


class CloseScene(_SceneBase):
    layout: Literal["close"]
    content: CloseContent


Scene = Annotated[
    Union[
        HeroScene, StatementScene, StatTrioScene, TwoColumnScene,
        ArchitectureScene, BarChartScene, TimelineScene, TeamScene, CloseScene,
    ],
    Field(discriminator="layout"),
]


# ---------------------------------------------------------------------------
# Deck Spec
# ---------------------------------------------------------------------------

class DeckSpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    brand_id: str = Field(alias="brandId", min_length=1, max_length=120)  # Brand.slug
    title: str = Field(min_length=1, max_length=300)
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = Field(default="16:9", alias="aspectRatio")
    # Free text: a stock speaker name (voice_mode=stock) or a persona identity
    # id/name (voice_mode=clone). Omit to use the brand/account default.
    voice: str | None = None
    scenes: list[Scene] = Field(min_length=1)

    @field_validator("scenes")
    @classmethod
    def _unique_scene_ids(cls, v: list) -> list:
        ids = [s.id for s in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Scene ids must be unique within a deck.")
        return v


# ---------------------------------------------------------------------------
# API request/response
# ---------------------------------------------------------------------------

class PitchVideoCreateRequest(BaseModel):
    deck_spec: dict = Field(description="Raw Deck Spec JSON — validated server-side.")


class PitchVideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    title: str
    aspect_ratio: str
    voice_mode: str
    speaker_name: str | None
    status: str
    progress_note: str | None
    estimated_seconds: int | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    has_output: bool = False

    @classmethod
    def from_job(cls, job) -> "PitchVideoOut":
        out = cls.model_validate(job)
        out.has_output = bool(job.output_path)
        return out


class StockSpeakersOut(BaseModel):
    speakers: list[str]
