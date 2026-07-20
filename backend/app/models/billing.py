"""Billing: subscription plan + Stripe identifiers (Phase 2 M3).

One Subscription row per Account — the source of truth for what the account
can do.  Stripe is the payment authority; we mirror just enough state here to
make entitlement checks fast (no Stripe API call per request).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import BaseModel


class PlanName(StrEnum):
    trial = "trial"
    pro = "pro"
    pro_max = "pro_max"
    premium = "premium"
    # Complimentary internal access, granted only by a platform admin from the
    # admin console — never offered at checkout, never touched by Stripe.
    comp = "comp"
    # Legacy tiers — retained so subscriptions created before the 2026-07-14
    # pricing change still resolve their entitlements. Not offered at checkout.
    agency = "agency"
    enterprise = "enterprise"


class SubscriptionStatus(StrEnum):
    trialing = "trialing"
    active = "active"
    past_due = "past_due"      # payment failed; Stripe grace period still active
    canceled = "canceled"
    incomplete = "incomplete"  # checkout started but not completed


class Subscription(BaseModel, table=True):
    """One row per Account — mirrors the Stripe subscription state locally."""

    __tablename__ = "subscriptions"

    account_id: uuid.UUID = Field(
        foreign_key="accounts.id", index=True, unique=True
    )
    plan: PlanName = Field(
        default=PlanName.trial, sa_type=sa.String, max_length=20, index=True
    )
    status: SubscriptionStatus = Field(
        default=SubscriptionStatus.trialing, sa_type=sa.String, max_length=20, index=True
    )
    # Trial window — None once converted to a paid plan.
    trial_ends_at: datetime | None = Field(default=None)
    # Current billing period end — populated from Stripe.
    current_period_end: datetime | None = Field(default=None)

    # Stripe identifiers — empty until the first checkout completes.
    stripe_customer_id: str | None = Field(default=None, max_length=100, index=True)
    stripe_subscription_id: str | None = Field(default=None, max_length=100, index=True)
    stripe_price_id: str | None = Field(default=None, max_length=100)
    billing_interval: str | None = Field(default=None, max_length=10)  # "monthly" | "annual"

    # Populated when the subscription is canceled.
    canceled_at: datetime | None = Field(default=None)
    # True when the user has requested cancellation at period end (access continues
    # until current_period_end; Stripe will set status=canceled on that date).
    cancel_at_period_end: bool = Field(default=False)
