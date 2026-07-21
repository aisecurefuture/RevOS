"""Certifications & reviews — verifiable trust signals (Phase 3, RK1).

Two entities feed the future brand/product rating engine (RK2) and the
creator's own reputation:

- **Certification** — a verifiable credential attached to a Creator or a
  MatchProduct (industry or quality-control certifications, "review history"
  in the roadmap's words made concrete). Tenant-owned, like the subject it's
  attached to. A platform admin can mark one ``verified`` after checking it.

- **Review** — feedback left by one party about the OTHER side of a real,
  completed collaboration. Always tied to a ``CollaborationRequest`` — no
  collaboration, no review, which is what keeps reviews honest. Cross-tenant
  by nature (the reviewer and the subject are different tenants), so like
  ``CollaborationRequest`` this is a plain ``BaseModel``, not tenant-scoped.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import BaseModel, TenantModel


class CertificationSubjectType(StrEnum):
    creator = "creator"
    match_product = "match_product"


class CertificationStatus(StrEnum):
    active = "active"
    expired = "expired"
    revoked = "revoked"


class Certification(TenantModel, table=True):
    """A credential attached to a creator or product — industry/quality-control
    certs, awards, or verified affiliations. Polymorphic subject, mirroring the
    entity_type/entity_id pattern already used by ApprovalRequest."""

    __tablename__ = "certifications"

    subject_type: CertificationSubjectType = Field(sa_type=sa.String, max_length=20, index=True)
    subject_id: uuid.UUID = Field(index=True)

    name: str = Field(max_length=200)               # e.g. "BBB Accredited Business"
    issuer: str | None = Field(default=None, max_length=200)
    certificate_number: str | None = Field(default=None, max_length=120)
    verification_url: str | None = Field(default=None, max_length=500)

    issued_at: datetime | None = Field(default=None)
    expires_at: datetime | None = Field(default=None, index=True)
    status: CertificationStatus = Field(
        default=CertificationStatus.active, sa_type=sa.String, max_length=16, index=True,
    )

    # Platform-admin verification — a self-reported cert vs one RevOS confirmed.
    verified: bool = Field(default=False, index=True)
    verified_at: datetime | None = Field(default=None)
    verified_by_user_id: uuid.UUID | None = Field(default=None, foreign_key="admin_users.id")


class ReviewDirection(StrEnum):
    brand_reviews_creator = "brand_reviews_creator"
    creator_reviews_brand = "creator_reviews_brand"


class Review(BaseModel, table=True):
    """Feedback left after a completed collaboration. NOT tenant-scoped (see
    module docstring) — queried explicitly by subject or by reviewer account.

    One review per (collaboration, reviewer) — enforced by a unique constraint
    — so a party can't flood a single engagement with repeat reviews.
    """

    __tablename__ = "reviews"

    collaboration_request_id: uuid.UUID = Field(foreign_key="collaboration_requests.id", index=True)
    direction: ReviewDirection = Field(sa_type=sa.String, max_length=24, index=True)

    reviewer_account_id: uuid.UUID = Field(foreign_key="accounts.id", index=True)
    reviewer_user_id: uuid.UUID = Field(foreign_key="admin_users.id", index=True)

    # The party being reviewed — exactly one is set, matching `direction`.
    subject_creator_id: uuid.UUID | None = Field(default=None, foreign_key="creators.id", index=True)
    subject_product_id: uuid.UUID | None = Field(default=None, foreign_key="match_products.id", index=True)

    rating: int = Field(ge=1, le=5)
    # Optional per-dimension ratings, e.g. {"communication": 5, "reliability": 4,
    # "quality": 5, "payment_promptness": 5} — free-form, keyed by whatever
    # dimensions RK2 defines, so this model doesn't need to change when they do.
    dimension_ratings: dict = Field(default_factory=dict, sa_type=sa.JSON)
    comment: str | None = Field(default=None, max_length=2000)

    # The reviewed party's own public reply, e.g. addressing a bad review.
    response: str | None = Field(default=None, max_length=2000)
    response_at: datetime | None = Field(default=None)

    __table_args__ = (
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_review_rating_range"),
        sa.UniqueConstraint("collaboration_request_id", "reviewer_account_id",
                            name="uq_review_collaboration_reviewer"),
    )
