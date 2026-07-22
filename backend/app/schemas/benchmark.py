"""Third-party industry benchmark schemas (BM1)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.industry_taxonomy import CATEGORIES

_PLATFORMS = {"all", "facebook", "instagram", "linkedin", "threads", "tiktok", "twitter", "youtube"}


class IndustryBenchmarkCreate(BaseModel):
    industry_category: str
    platform: str = "all"
    metric: str = Field(default="engagement_rate", max_length=40)
    value: float
    source: str = Field(min_length=1, max_length=200)
    source_url: str | None = Field(default=None, max_length=500)
    period_label: str = Field(min_length=1, max_length=40)

    @field_validator("industry_category")
    @classmethod
    def _valid_category(cls, v: str) -> str:
        if v not in CATEGORIES:
            raise ValueError(f"industry_category must be one of: {', '.join(CATEGORIES)}")
        return v

    @field_validator("platform")
    @classmethod
    def _valid_platform(cls, v: str) -> str:
        if v not in _PLATFORMS:
            raise ValueError(f"platform must be one of: {', '.join(sorted(_PLATFORMS))}")
        return v


class IndustryBenchmarkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    industry_category: str
    platform: str
    metric: str
    value: float
    source: str
    source_url: str | None = None
    period_label: str
    updated_by_user_id: uuid.UUID
    updated_at: datetime


class BenchmarkExtractRequest(BaseModel):
    """Paste-and-parse assist (BM3): raw report text in, draft rows out for
    the admin to review before anything saves."""

    text: str = Field(min_length=1, max_length=20000)
    source: str = Field(min_length=1, max_length=200)
    source_url: str | None = Field(default=None, max_length=500)
    period_label: str = Field(min_length=1, max_length=40)


class BenchmarkExtractRow(BaseModel):
    industry_category: str
    platform: str
    metric: str
    value: float


class BenchmarkExtractResult(BaseModel):
    rows: list[BenchmarkExtractRow]
    unparsed_note: str | None = None
