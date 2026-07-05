"""Per-account low-cost integration credentials (Phase 3).

One row per (account, provider). Secrets (API keys, service-account JSON,
inbound signing secrets) are never stored here — only a reference to the
OpenBao KV path (``secret_ref``). Non-secret configuration (database IDs,
spreadsheet IDs, a Calendly scheduling URL, a Zapier outbound webhook URL)
lives in ``config``.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, TenantModel


class IntegrationProvider(StrEnum):
    calendly = "calendly"
    notion = "notion"
    bitly = "bitly"
    zapier = "zapier"
    google_sheets = "google_sheets"


class IntegrationCredentialStatus(StrEnum):
    active = "active"
    error = "error"


class IntegrationCredential(TenantModel, table=True):
    __tablename__ = "integration_credentials"
    __table_args__ = (
        sa.UniqueConstraint("account_id", "provider", name="uq_integration_credential_account_provider"),
    )

    provider: IntegrationProvider = Field(sa_type=sa.String(20), index=True)
    config: dict = Field(default_factory=dict, sa_type=JSON)
    secret_ref: str | None = Field(default=None, max_length=500)
    status: IntegrationCredentialStatus = Field(
        default=IntegrationCredentialStatus.active, sa_type=sa.String(16),
    )
    connected_by: uuid.UUID = Field(foreign_key="admin_users.id", index=True)
