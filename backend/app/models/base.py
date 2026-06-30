"""Shared model primitives: UUID PK, timestamps, soft-delete, enums, JSON.

Design choices:
- **String-backed enums** (StrEnum + `sa_type=String`) instead of native
  Postgres ENUM types, so adding a new status never needs an `ALTER TYPE`
  migration.
- **Python-side timestamp defaults** (not DB `server_default`) so the schema is
  portable across Postgres (prod) and SQLite (fast tests).
- Reserved attribute `metadata` is never used as a column name (SQLAlchemy owns
  it); flexible blobs are named `meta` / `settings` / `details` / `properties`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Naive UTC now. The DB stores TIMESTAMP WITHOUT TIME ZONE (UTC by
    convention); returning a naive value keeps inserts/comparisons consistent
    across Postgres (asyncpg rejects tz-aware values for naive columns) and
    SQLite. All timestamps in RevOS are UTC."""
    return datetime.now(UTC).replace(tzinfo=None)


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class IDModel(SQLModel):
    """UUID primary key."""

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True, index=True)


class TimestampModel(SQLModel):
    """Created/updated timestamps + soft-delete marker."""

    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column_kwargs={"onupdate": utcnow},
        nullable=False,
    )
    # Soft delete: rows are filtered, not physically removed, to preserve audit
    # trails and downstream FK integrity.
    deleted_at: datetime | None = Field(default=None, index=True)


class BaseModel(IDModel, TimestampModel):
    """Common base for all RevOS tables (UUID + timestamps + soft-delete)."""


# Convenience JSON column type. Generic `sa.JSON` is portable (Postgres + SQLite
# in tests). Switch to postgresql.JSONB via an Alembic migration if/when GIN
# indexing on these blobs is needed.
JSON = sa.JSON
