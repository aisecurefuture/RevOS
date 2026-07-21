"""Inbound social comments + their approval-gated AI replies (P?-comments).

One row per comment ingested from a connected Facebook Page or Instagram
Business account. A relevance filter decides which comments are worth a
reply; those get an AI-drafted response (grounded in the brand's voice +
Brand Book and, when set, a Persona), which lands as a pending
ApprovalRequest. Nothing is posted until the account owner approves it on
the Approvals page — the same governance model as every other RevOS action.

Liking a comment (Facebook only via the Graph API) is a one-click action
recorded here as well.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import BaseModel, TenantModel


class SocialCommentStatus(StrEnum):
    new = "new"            # ingested, relevance-passed, not yet drafted
    drafted = "drafted"    # AI reply drafted → ApprovalRequest pending
    replied = "replied"    # reply posted after approval
    ignored = "ignored"    # filtered out or dismissed by a human
    failed = "failed"      # reply attempt failed


class SocialComment(TenantModel, table=True):
    __tablename__ = "social_comments"
    __table_args__ = (
        # One row per platform comment — the ingest poller dedupes on this.
        sa.UniqueConstraint("account_id", "external_comment_id", name="uq_social_comment_external"),
    )

    connection_id: uuid.UUID = Field(foreign_key="social_connections.id", index=True)
    brand_id: uuid.UUID | None = Field(default=None, foreign_key="brands.id", index=True)

    platform: str = Field(sa_type=sa.String(20), index=True)  # facebook | instagram
    external_post_id: str = Field(max_length=200)
    external_comment_id: str = Field(max_length=200, index=True)
    permalink: str | None = Field(default=None, max_length=600)

    author_name: str | None = Field(default=None, max_length=200)
    author_external_id: str | None = Field(default=None, max_length=200)
    text: str = Field(sa_type=sa.Text)
    posted_at: datetime | None = Field(default=None)

    status: SocialCommentStatus = Field(
        default=SocialCommentStatus.new, sa_type=sa.String(16), index=True,
    )
    # Why the relevance filter let this through (or, for ignored, why it was
    # dropped) — surfaced to the reviewer for context.
    relevance_note: str | None = Field(default=None, max_length=300)

    drafted_reply: str | None = Field(default=None, sa_type=sa.Text)
    approval_id: uuid.UUID | None = Field(
        default=None, foreign_key="approval_requests.id", index=True,
    )
    reply_external_id: str | None = Field(default=None, max_length=200)
    liked: bool = Field(default=False)
    error: str | None = Field(default=None, sa_type=sa.Text)
