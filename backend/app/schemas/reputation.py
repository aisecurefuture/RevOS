"""Certification & review schemas (RK1)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.reputation import CertificationStatus, CertificationSubjectType, ReviewDirection


# --- Certification -----------------------------------------------------------
class CertificationCreate(BaseModel):
    subject_type: CertificationSubjectType
    subject_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    issuer: str | None = Field(default=None, max_length=200)
    certificate_number: str | None = Field(default=None, max_length=120)
    verification_url: str | None = Field(default=None, max_length=500)
    issued_at: datetime | None = None
    expires_at: datetime | None = None


class CertificationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    issuer: str | None = Field(default=None, max_length=200)
    certificate_number: str | None = Field(default=None, max_length=120)
    verification_url: str | None = Field(default=None, max_length=500)
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    status: CertificationStatus | None = None


class CertificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject_type: str
    subject_id: uuid.UUID
    name: str
    issuer: str | None = None
    certificate_number: str | None = None
    verification_url: str | None = None
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    status: str
    verified: bool
    verified_at: datetime | None = None
    created_at: datetime


# --- Review -------------------------------------------------------------------
class ReviewCreate(BaseModel):
    collaboration_request_id: uuid.UUID
    rating: int = Field(ge=1, le=5)
    dimension_ratings: dict[str, int] = Field(default_factory=dict)
    comment: str | None = Field(default=None, max_length=2000)


class ReviewRespond(BaseModel):
    response: str = Field(min_length=1, max_length=2000)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    collaboration_request_id: uuid.UUID
    direction: ReviewDirection
    reviewer_account_id: uuid.UUID
    subject_creator_id: uuid.UUID | None = None
    subject_product_id: uuid.UUID | None = None
    rating: int
    dimension_ratings: dict = Field(default_factory=dict)
    comment: str | None = None
    response: str | None = None
    response_at: datetime | None = None
    created_at: datetime


# --- Reputation score (RK2) --------------------------------------------------
class ReputationDimensionOut(BaseModel):
    key: str
    score: float
    weight: float
    available: bool
    detail: str


class ReputationScoreOut(BaseModel):
    overall: float
    coverage: float
    review_count: int
    rationale: str
    dimensions: list[ReputationDimensionOut]
