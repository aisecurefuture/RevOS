"""Billing request/response schemas (Phase 2 M3)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CheckoutRequest(BaseModel):
    plan: Literal["pro", "agency"] = "pro"
    interval: Literal["monthly", "annual"] = "monthly"


class CheckoutResponse(BaseModel):
    checkout_url: str


class PortalResponse(BaseModel):
    portal_url: str


class PlanLimitsOut(BaseModel):
    seats: int | None
    brands: int | None
    contacts: int | None
    emails_per_month: int | None
    social_connections: int | None
    ai_drafts_per_month: int | None
    landing_pages: int | None
    api_access: bool
    client_workspaces: bool
    white_label: bool


class BillingStatusOut(BaseModel):
    plan: str
    effective_plan: str | None  # None = trial expired or subscription inactive
    status: str | None
    trial_ends_at: datetime | None
    current_period_end: datetime | None
    is_trial_expired: bool
    billing_interval: str | None  # "monthly" | "annual" | None
    limits: PlanLimitsOut
    prices: dict  # display-only price map in cents
