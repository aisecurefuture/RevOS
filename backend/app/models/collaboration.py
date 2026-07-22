"""Collaboration workspace (Phase 5 — CW1).

When a CollaborationRequest is ACCEPTED, it spawns a **Collaboration** — the
shared, cross-tenant project space where the brand and creator actually do the
work. One-off engagements and ongoing ambassador programs both live here.

CW1 delivers the foundation: the Collaboration itself, and **consent-gated,
time-boxed knowledge sharing** (``CollaborationShare``) — a party grants the
other side read access to a resource (v1: a Brand Book, reused via the
brand/creator's ``brand_id`` link, so nobody re-enters their homework). Access
is revocable, expirable, and auto-revoked when the collaboration ends.

Cross-tenant by nature (two accounts), so these are plain ``BaseModel``s (NOT
tenant-scoped) with explicit party account columns, queried per-side — same
pattern as CollaborationRequest.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import BaseModel


class CollaborationKind(StrEnum):
    one_off = "one_off"          # a single engagement
    ambassador = "ambassador"    # an ongoing / recurring program


class CollaborationState(StrEnum):
    active = "active"
    paused = "paused"
    completed = "completed"
    ended = "ended"              # closed out — shares auto-revoked


class Collaboration(BaseModel, table=True):
    __tablename__ = "collaborations"

    # 1:1 with the accepted request that spawned it.
    collaboration_request_id: uuid.UUID = Field(
        foreign_key="collaboration_requests.id", index=True, unique=True)

    brand_account_id: uuid.UUID = Field(foreign_key="accounts.id", index=True)
    creator_account_id: uuid.UUID = Field(foreign_key="accounts.id", index=True)
    creator_id: uuid.UUID = Field(foreign_key="creators.id", index=True)
    product_id: uuid.UUID | None = Field(default=None, foreign_key="match_products.id", index=True)

    kind: CollaborationKind = Field(
        default=CollaborationKind.one_off, sa_type=sa.String, max_length=16, index=True)
    state: CollaborationState = Field(
        default=CollaborationState.active, sa_type=sa.String, max_length=16, index=True)
    title: str | None = Field(default=None, max_length=250)
    ended_at: datetime | None = Field(default=None)


class SharedResourceType(StrEnum):
    brand_book = "brand_book"    # v1. CW2 will add: asset, document, etc.


class ShareStatus(StrEnum):
    active = "active"
    revoked = "revoked"
    expired = "expired"


class CollaborationShare(BaseModel, table=True):
    """One party granting the other read access to a resource within a
    collaboration. Polymorphic resource (mirrors Certification): for a
    brand_book, ``resource_id`` is the Brand's id (its book is 1:1 with it)."""

    __tablename__ = "collaboration_shares"

    collaboration_id: uuid.UUID = Field(foreign_key="collaborations.id", index=True)
    shared_by_account_id: uuid.UUID = Field(foreign_key="accounts.id", index=True)

    resource_type: SharedResourceType = Field(sa_type=sa.String, max_length=20, index=True)
    resource_id: uuid.UUID = Field(index=True)
    scope: str | None = Field(default=None, max_length=200)   # whole-resource for now; granular later

    expires_at: datetime | None = Field(default=None, index=True)
    revoked_at: datetime | None = Field(default=None)
    status: ShareStatus = Field(
        default=ShareStatus.active, sa_type=sa.String, max_length=16, index=True)

    __table_args__ = (
        sa.UniqueConstraint("collaboration_id", "resource_type", "resource_id",
                            "shared_by_account_id", name="uq_collab_share_resource"),
    )
