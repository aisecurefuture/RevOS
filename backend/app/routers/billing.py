"""Billing router (Phase 2 M3).

Endpoints:
  GET  /api/billing/status   — current plan, limits, trial state
  POST /api/billing/checkout — Stripe Checkout session → redirect URL
  POST /api/billing/portal   — Stripe Customer Portal → redirect URL
  POST /api/billing/webhook  — Stripe webhook (no auth, signature-verified)

Pricing (as of 2026-07-14):
  Pro      $1,999.99/mo | $19,200/yr
  Pro Max  $3,999.99/mo | $38,400/yr
  Premium  $5,999.99/mo | $57,600/yr
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Request

from app.core.entitlements import get_effective_plan, get_plan_limits, is_trial_expired
from app.core.exceptions import AuthError, PermissionError_
from app.core.rate_limit import rate_limit
from app.deps import CurrentUser, DbSession, verify_csrf
from app.models.billing import PlanName
from app.schemas.billing import (
    BillingStatusOut,
    CheckoutRequest,
    CheckoutResponse,
    PlanLimitsOut,
    PortalResponse,
)
from app.services import billing_service
from app.services.stripe_service import verify_webhook

logger = logging.getLogger("revos.billing")
router = APIRouter(prefix="/billing", tags=["billing"])

_webhook_rl = rate_limit("billing_webhook", "120/minute")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@router.get("/status", response_model=BillingStatusOut)
async def billing_status(request: Request, user: CurrentUser, db: DbSession) -> BillingStatusOut:
    """Return the active account's plan, limits, and trial state."""
    account_id = getattr(request.state, "account_id", None)
    if account_id is None:
        raise PermissionError_("No active account context.")

    sub = await billing_service.get_subscription(db, account_id)
    effective = get_effective_plan(sub)
    limits = get_plan_limits(sub)
    expired = is_trial_expired(sub)

    from app.config import settings as cfg
    prices = {
        "pro_monthly_cents": cfg.plan_pro_monthly_cents,
        "pro_annual_cents": cfg.plan_pro_annual_cents,
        "pro_max_monthly_cents": cfg.plan_pro_max_monthly_cents,
        "pro_max_annual_cents": cfg.plan_pro_max_annual_cents,
        "premium_monthly_cents": cfg.plan_premium_monthly_cents,
        "premium_annual_cents": cfg.plan_premium_annual_cents,
    }

    return BillingStatusOut(
        plan=sub.plan if sub else PlanName.trial,
        effective_plan=effective,
        status=sub.status if sub else None,
        trial_ends_at=sub.trial_ends_at if sub else None,
        current_period_end=sub.current_period_end if sub else None,
        is_trial_expired=expired,
        cancel_at_period_end=sub.cancel_at_period_end if sub else False,
        billing_interval=sub.billing_interval if sub else None,
        limits=PlanLimitsOut(
            seats=limits.seats,
            brands=limits.brands,
            contacts=limits.contacts,
            emails_per_month=limits.emails_per_month,
            social_connections=limits.social_connections,
            ai_drafts_per_month=limits.ai_drafts_per_month,
            landing_pages=limits.landing_pages,
            api_access=limits.api_access,
            client_workspaces=limits.client_workspaces,
            white_label=limits.white_label,
        ),
        prices=prices,
    )


# ---------------------------------------------------------------------------
# Trial provisioning
# ---------------------------------------------------------------------------

@router.post("/start-trial", response_model=BillingStatusOut)
async def start_trial(
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _c: None = Depends(verify_csrf),
) -> BillingStatusOut:
    """Provision a 14-day trial for the current account.

    Idempotent — calling it when a subscription already exists is a no-op.
    This is the gate users hit after registration before entering the dashboard.
    """
    account_id = getattr(request.state, "account_id", None)
    if account_id is None:
        raise PermissionError_("No active account context.")

    sub = await billing_service.get_subscription(db, account_id)
    if sub is None:
        sub = await billing_service.provision_trial(db, account_id)

    from app.config import settings as cfg
    effective = get_effective_plan(sub)
    limits = get_plan_limits(sub)
    expired = is_trial_expired(sub)
    prices = {
        "pro_monthly_cents": cfg.plan_pro_monthly_cents,
        "pro_annual_cents": cfg.plan_pro_annual_cents,
        "pro_max_monthly_cents": cfg.plan_pro_max_monthly_cents,
        "pro_max_annual_cents": cfg.plan_pro_max_annual_cents,
        "premium_monthly_cents": cfg.plan_premium_monthly_cents,
        "premium_annual_cents": cfg.plan_premium_annual_cents,
    }
    return BillingStatusOut(
        plan=sub.plan,
        effective_plan=effective,
        status=sub.status,
        trial_ends_at=sub.trial_ends_at,
        current_period_end=sub.current_period_end,
        is_trial_expired=expired,
        cancel_at_period_end=sub.cancel_at_period_end,
        billing_interval=sub.billing_interval,
        limits=PlanLimitsOut(
            seats=limits.seats,
            brands=limits.brands,
            contacts=limits.contacts,
            emails_per_month=limits.emails_per_month,
            social_connections=limits.social_connections,
            ai_drafts_per_month=limits.ai_drafts_per_month,
            landing_pages=limits.landing_pages,
            api_access=limits.api_access,
            client_workspaces=limits.client_workspaces,
            white_label=limits.white_label,
        ),
        prices=prices,
    )


# ---------------------------------------------------------------------------
# Checkout + portal
# ---------------------------------------------------------------------------

@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _c: None = Depends(verify_csrf),
) -> CheckoutResponse:
    """Create a Stripe Checkout session and return the redirect URL."""
    account_id = getattr(request.state, "account_id", None)
    if account_id is None:
        raise PermissionError_("No active account context.")

    url = await billing_service.create_checkout_session(
        db, account_id, user, body.plan, body.interval
    )
    return CheckoutResponse(checkout_url=url)


@router.post("/portal", response_model=PortalResponse)
async def create_portal(
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _c: None = Depends(verify_csrf),
) -> PortalResponse:
    """Create a Stripe Customer Portal session and return the redirect URL."""
    account_id = getattr(request.state, "account_id", None)
    if account_id is None:
        raise PermissionError_("No active account context.")

    url = await billing_service.create_portal_session(db, account_id)
    return PortalResponse(portal_url=url)


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

@router.post("/cancel", response_model=BillingStatusOut)
async def cancel_subscription(
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _c: None = Depends(verify_csrf),
) -> BillingStatusOut:
    """Schedule the subscription to cancel at the end of the current billing period."""
    account_id = getattr(request.state, "account_id", None)
    if account_id is None:
        raise PermissionError_("No active account context.")

    sub = await billing_service.cancel_subscription(db, account_id)

    from app.config import settings as cfg
    effective = get_effective_plan(sub)
    limits = get_plan_limits(sub)
    expired = is_trial_expired(sub)
    prices = {
        "pro_monthly_cents": cfg.plan_pro_monthly_cents,
        "pro_annual_cents": cfg.plan_pro_annual_cents,
        "pro_max_monthly_cents": cfg.plan_pro_max_monthly_cents,
        "pro_max_annual_cents": cfg.plan_pro_max_annual_cents,
        "premium_monthly_cents": cfg.plan_premium_monthly_cents,
        "premium_annual_cents": cfg.plan_premium_annual_cents,
    }
    return BillingStatusOut(
        plan=sub.plan,
        effective_plan=effective,
        status=sub.status,
        trial_ends_at=sub.trial_ends_at,
        current_period_end=sub.current_period_end,
        is_trial_expired=expired,
        cancel_at_period_end=sub.cancel_at_period_end,
        billing_interval=sub.billing_interval,
        limits=PlanLimitsOut(
            seats=limits.seats,
            brands=limits.brands,
            contacts=limits.contacts,
            emails_per_month=limits.emails_per_month,
            social_connections=limits.social_connections,
            ai_drafts_per_month=limits.ai_drafts_per_month,
            landing_pages=limits.landing_pages,
            api_access=limits.api_access,
            client_workspaces=limits.client_workspaces,
            white_label=limits.white_label,
        ),
        prices=prices,
    )


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: DbSession,
    _rl: None = Depends(_webhook_rl),
) -> dict:
    """Receive and process Stripe lifecycle events.

    Signature is verified before any state change.
    Unverified or malformed requests are rejected with 401.
    """
    raw = await request.body()
    sig = request.headers.get("stripe-signature", "")

    if not verify_webhook(raw, sig):
        raise AuthError("Invalid Stripe webhook signature.")

    try:
        event = json.loads(raw.decode())
    except (ValueError, UnicodeDecodeError) as exc:
        raise AuthError("Malformed webhook payload.") from exc

    event_type = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}
    handled = False

    if event_type == "checkout.session.completed":
        handled = await billing_service.handle_checkout_completed(db, obj)
    elif event_type == "customer.subscription.updated":
        handled = await billing_service.handle_subscription_updated(db, obj)
    elif event_type == "customer.subscription.deleted":
        handled = await billing_service.handle_subscription_deleted(db, obj)
    else:
        # Also hand off to the Phase 1 offer/revenue handler.
        from app.services.stripe_service import handle_event as p1_handle
        handled = await p1_handle(db, event)

    return {"received": True, "handled": handled, "type": event_type}
