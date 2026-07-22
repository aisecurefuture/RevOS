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


# --- CW2: shared assets + two-sided review-before-post ----------------------
class AssetKind(StrEnum):
    text = "text"
    image = "image"
    video = "video"


class AssetState(StrEnum):
    draft = "draft"                    # a version exists, no decision recorded yet on it
    in_review = "in_review"            # at least one party has weighed in
    changes_requested = "changes_requested"
    approved = "approved"              # both parties approved the CURRENT version
    published = "published"            # handed off to the real publishing pipeline


class ApprovalDecision(StrEnum):
    approved = "approved"
    changes_requested = "changes_requested"


class CollaborationAsset(BaseModel, table=True):
    """A piece of content being drafted inside a collaboration — text, image,
    or video — that both sides review before it's posted. Versioned: each edit
    is a new ``CollaborationAssetVersion``; approvals are recorded per-version,
    so a new draft always needs fresh sign-off from both parties."""

    __tablename__ = "collaboration_assets"

    collaboration_id: uuid.UUID = Field(foreign_key="collaborations.id", index=True)
    created_by_account_id: uuid.UUID = Field(foreign_key="accounts.id", index=True)

    kind: AssetKind = Field(sa_type=sa.String, max_length=10, index=True)
    title: str | None = Field(default=None, max_length=250)
    current_version: int = Field(default=1)
    state: AssetState = Field(default=AssetState.draft, sa_type=sa.String, max_length=20, index=True)

    # Set once this asset is handed off to a real SocialPost (the existing
    # content/social publishing + approval pipeline takes over from there).
    linked_social_post_id: uuid.UUID | None = Field(default=None, index=True)


class CollaborationAssetVersion(BaseModel, table=True):
    __tablename__ = "collaboration_asset_versions"

    asset_id: uuid.UUID = Field(foreign_key="collaboration_assets.id", index=True)
    version: int = Field(index=True)
    created_by_account_id: uuid.UUID = Field(foreign_key="accounts.id", index=True)

    caption: str | None = Field(default=None, sa_type=sa.Text)
    media_urls: list = Field(default_factory=list, sa_type=sa.JSON)

    __table_args__ = (
        sa.UniqueConstraint("asset_id", "version", name="uq_asset_version"),
    )


class CollaborationAssetComment(BaseModel, table=True):
    __tablename__ = "collaboration_asset_comments"

    asset_id: uuid.UUID = Field(foreign_key="collaboration_assets.id", index=True)
    version: int | None = Field(default=None)   # None = general comment, not version-specific
    author_account_id: uuid.UUID = Field(foreign_key="accounts.id", index=True)
    author_user_id: uuid.UUID = Field(foreign_key="admin_users.id", index=True)
    body: str = Field(max_length=2000)


class CollaborationAssetApproval(BaseModel, table=True):
    """One party's decision on a specific version. Re-deciding on the same
    version overwrites (upsert, enforced by the unique constraint); a new
    version simply has no rows yet, so prior decisions never carry forward."""

    __tablename__ = "collaboration_asset_approvals"

    asset_id: uuid.UUID = Field(foreign_key="collaboration_assets.id", index=True)
    version: int = Field(index=True)
    account_id: uuid.UUID = Field(foreign_key="accounts.id", index=True)
    user_id: uuid.UUID = Field(foreign_key="admin_users.id")
    decision: ApprovalDecision = Field(sa_type=sa.String, max_length=20)
    note: str | None = Field(default=None, max_length=1000)

    __table_args__ = (
        sa.UniqueConstraint("asset_id", "version", "account_id", name="uq_asset_approval_party"),
    )


# --- CW3: briefs, deliverables, disclosure & usage rights --------------------
class DeliverableStatus(StrEnum):
    pending = "pending"
    in_progress = "in_progress"
    delivered = "delivered"
    approved = "approved"


class CollaborationBrief(BaseModel, table=True):
    """1:1 with a Collaboration — a shared, co-authored brief. Either party may
    edit; the last editor is tracked, not a per-field lock (simple, matches how
    a real shared doc gets negotiated). Carries the compliance substrate the
    roadmap calls for: FTC disclosure requirements and content usage/licensing
    terms, agreed up front rather than argued about after a post goes live."""

    __tablename__ = "collaboration_briefs"

    collaboration_id: uuid.UUID = Field(foreign_key="collaborations.id", index=True, unique=True)
    updated_by_account_id: uuid.UUID = Field(foreign_key="accounts.id")

    goals: str | None = Field(default=None, sa_type=sa.Text)
    key_messages: list = Field(default_factory=list, sa_type=sa.JSON)
    dos: list = Field(default_factory=list, sa_type=sa.JSON)
    donts: list = Field(default_factory=list, sa_type=sa.JSON)
    deadline: datetime | None = Field(default=None)

    # Disclosure (FTC #ad etc.) — on by default; a party has to consciously
    # turn it off, not consciously turn it on.
    requires_disclosure: bool = Field(default=True)
    disclosure_text: str | None = Field(default=None, max_length=200)   # e.g. "#ad #sponsored"

    # Usage / licensing rights.
    usage_rights: str | None = Field(default=None, sa_type=sa.Text)
    usage_duration_days: int | None = Field(default=None)   # None = unspecified/perpetual
    whitelisting_allowed: bool = Field(default=False)
    boost_allowed: bool = Field(default=False)


class CollaborationDeliverable(BaseModel, table=True):
    """One concrete deliverable in a collaboration's plan, e.g. "3 posts + 1
    reel by Fri" — tracked to completion, optionally linked to the
    CollaborationAsset that fulfills it once drafted."""

    __tablename__ = "collaboration_deliverables"

    collaboration_id: uuid.UUID = Field(foreign_key="collaborations.id", index=True)
    created_by_account_id: uuid.UUID = Field(foreign_key="accounts.id", index=True)

    title: str = Field(max_length=250)
    description: str | None = Field(default=None, sa_type=sa.Text)
    due_at: datetime | None = Field(default=None, index=True)
    status: DeliverableStatus = Field(
        default=DeliverableStatus.pending, sa_type=sa.String, max_length=16, index=True)
    asset_id: uuid.UUID | None = Field(default=None, foreign_key="collaboration_assets.id", index=True)
    completed_at: datetime | None = Field(default=None)


class CollaborationMessage(BaseModel, table=True):
    """A free-form message in a collaboration's thread — unlocked only after
    acceptance (the workspace exists), unlike CollaborationRequest's single
    pre-accept message. "Block" is the existing end_collaboration action (either
    party can end the collaboration unilaterally, which stops new messages);
    "report" flags a message for platform-admin review without deleting it."""

    __tablename__ = "collaboration_messages"

    collaboration_id: uuid.UUID = Field(foreign_key="collaborations.id", index=True)
    sender_account_id: uuid.UUID = Field(foreign_key="accounts.id", index=True)
    sender_user_id: uuid.UUID = Field(foreign_key="admin_users.id", index=True)
    body: str = Field(max_length=4000)

    is_flagged: bool = Field(default=False, index=True)
    flagged_by_account_id: uuid.UUID | None = Field(default=None, foreign_key="accounts.id")
    flagged_reason: str | None = Field(default=None, max_length=500)
    flagged_at: datetime | None = Field(default=None)
