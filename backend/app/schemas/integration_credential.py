"""Schemas for per-account low-cost integration credentials (Phase 3)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CalendlyRequest(BaseModel):
    scheduling_url: str = Field(min_length=1, max_length=500)


class NotionRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=300)
    database_id: str = Field(min_length=1, max_length=200)


class BitlyRequest(BaseModel):
    access_token: str = Field(min_length=1, max_length=300)


class GoogleSheetsRequest(BaseModel):
    service_account_json: str
    spreadsheet_id: str = Field(min_length=1, max_length=200)


class ZapierRequest(BaseModel):
    outbound_webhook_url: str | None = Field(default=None, max_length=1000)


class IntegrationCredentialOut(BaseModel):
    provider: str
    config: dict
    status: str


class ZapierSaveOut(BaseModel):
    credential: IntegrationCredentialOut
    inbound_webhook_url: str
    # Only present the moment the secret is generated (first save) or rotated —
    # never returned again after that, same as 2FA recovery codes.
    inbound_secret: str | None = None


class ShortenRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


class ShortenOut(BaseModel):
    short_url: str


class PushContactsOut(BaseModel):
    pushed: int
