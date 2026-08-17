from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import false

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), default="")
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    subscription_status: Mapped[str] = mapped_column(String(32), default="inactive", index=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    saved_listings: Mapped[list[SavedListing]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def has_access(self) -> bool:
        return self.subscription_status in {"active", "trialing"}


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_listing_source_external"),
        Index("ix_listings_rank", "status", "deal_score"),
        Index("ix_listings_geography", "state", "county"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    address: Mapped[str] = mapped_column(String(500), default="")
    city: Mapped[str] = mapped_column(String(120), default="")
    state: Mapped[str] = mapped_column(String(2), default="IL")
    postal_code: Mapped[str] = mapped_column(String(20), default="")
    county: Mapped[str] = mapped_column(String(120), default="")
    property_type: Mapped[str] = mapped_column(String(80), default="unknown")
    instrument_type: Mapped[str] = mapped_column(String(80), default="direct_sale")
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    auction_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auction_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    current_bid: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    starting_bid: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    deposit_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    estimated_market_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    repair_estimate: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    other_costs: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    estimated_profit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    profit_margin: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    deal_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    confidence: Mapped[str] = mapped_column(String(24), default="low")
    score_factors: Mapped[dict] = mapped_column(JSON, default=dict)
    source_url: Mapped[str] = mapped_column(Text)
    contact_name: Mapped[str] = mapped_column(String(200), default="")
    contact_email: Mapped[str] = mapped_column(String(320), default="")
    contact_phone: Mapped[str] = mapped_column(String(80), default="")
    how_to_buy: Mapped[list] = mapped_column(JSON, default=list)
    due_diligence: Mapped[list] = mapped_column(JSON, default=list)
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SavedListing(Base):
    __tablename__ = "saved_listings"
    __table_args__ = (UniqueConstraint("user_id", "listing_id", name="uq_saved_user_listing"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="saved_listings")
    listing: Mapped[Listing] = relationship()


class SourceStatus(Base):
    __tablename__ = "source_statuses"

    slug: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    official_url: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(40), default="listing_feed")
    refresh_interval_minutes: Mapped[int] = mapped_column(Integer, default=15)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    health: Mapped[str] = mapped_column(String(24), default="pending")
    last_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_found: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    etag: Mapped[str] = mapped_column(String(255), default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    # When the watched page last actually changed. For a calendar_monitor this
    # is the entire product of the source, so it has to be recorded and shown.
    last_change_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshRun(Base):
    __tablename__ = "refresh_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    trigger: Mapped[str] = mapped_column(String(32), default="scheduled")
    status: Mapped[str] = mapped_column(String(24), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discovered: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    # The watched page differed from the last fetch. For monitor-only sources
    # this is the only meaningful outcome a run can report. server_default lets
    # it be added to an existing, populated table (see database._sync_columns).
    changed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    error: Mapped[str] = mapped_column(Text, default="")


class ContactMessage(Base):
    """Accounting row for one delivered contact-form email.

    Deliberately holds no message content and no plaintext address — the
    operator's mailbox is the record. This table exists so the daily send cap
    survives a restart, which an in-memory counter would not.
    """

    __tablename__ = "contact_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    topic: Mapped[str] = mapped_column(String(40), default="")
    email_hash: Mapped[str] = mapped_column(String(64), default="")
    client_hash: Mapped[str] = mapped_column(String(64), default="")


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(120))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EmailLoginCode(Base):
    __tablename__ = "email_login_codes"
    __table_args__ = (Index("ix_login_code_email_created", "email", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    requested_ip: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthIdentity(Base):
    __tablename__ = "auth_identities"
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_identity_provider_subject"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(255))
    email_at_link: Mapped[str] = mapped_column(String(320), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PasskeyCredential(Base):
    __tablename__ = "passkey_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    credential_id: Mapped[str] = mapped_column(String(1024), unique=True, index=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    transports: Mapped[list] = mapped_column(JSON, default=list)
    device_type: Mapped[str] = mapped_column(String(40), default="unknown")
    backed_up: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
