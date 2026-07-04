"""Stripe billing service (Phase 2 M3).

Keeps all Stripe SDK calls in one place so they're easy to mock in tests.
Degrades gracefully when Stripe is not configured (STRIPE_SECRET_KEY unset).

Flow:
  1. Account created → provision_trial() → 14-day trial row in subscriptions
  2. User clicks Upgrade → create_checkout_session() → redirect to Stripe
  3. Stripe sends checkout.session.completed webhook → handle_checkout_completed()
  4. Stripe sends subscription lifecycle events → handle_subscription_updated/deleted()
  5. Celery task (hourly) → check for expired trials, send reminder emails
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.core.entitlements import PLAN_LIMITS, get_effective_plan, get_plan_limits
from app.core.exceptions import NotFoundError, PaymentRequiredError, RevOSError
from app.models.base import utcnow
from app.models.billing import PlanName, Subscription, SubscriptionStatus
from app.models.user import AdminUser

logger = logging.getLogger("revos.billing")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stripe():
    """Return the stripe module, configured. Raises if Stripe is not set up."""
    if not settings.stripe_secret_key:
        raise RevOSError("Stripe is not configured.", status_code=503, code="stripe_unconfigured")
    import stripe as _stripe_mod
    _stripe_mod.api_key = settings.stripe_secret_key
    return _stripe_mod


_PRICE_MAP: dict[tuple[str, str], str] = {}


def _price_id(plan: str, interval: str) -> str | None:
    """Look up the Stripe price ID for a plan + interval from settings."""
    return {
        ("pro", "monthly"): settings.stripe_pro_monthly_price_id,
        ("pro", "annual"): settings.stripe_pro_annual_price_id,
        ("agency", "monthly"): settings.stripe_agency_monthly_price_id,
        ("agency", "annual"): settings.stripe_agency_annual_price_id,
    }.get((plan, interval)) or None


def _plan_from_price_id(pid: str) -> PlanName:
    """Reverse-map a Stripe price ID → our PlanName. Defaults to pro."""
    if pid in (settings.stripe_pro_monthly_price_id, settings.stripe_pro_annual_price_id):
        return PlanName.pro
    if pid in (settings.stripe_agency_monthly_price_id, settings.stripe_agency_annual_price_id):
        return PlanName.agency
    return PlanName.pro


def _interval_from_price_id(pid: str) -> str:
    if pid in (settings.stripe_pro_annual_price_id, settings.stripe_agency_annual_price_id):
        return "annual"
    return "monthly"


# ---------------------------------------------------------------------------
# Read helpers (no Stripe calls)
# ---------------------------------------------------------------------------

async def get_subscription(db: AsyncSession, account_id: uuid.UUID) -> Subscription | None:
    res = await db.execute(
        select(Subscription).where(Subscription.account_id == account_id)
    )
    return res.scalar_one_or_none()


async def get_plan_limits_for_account(db: AsyncSession, account_id: uuid.UUID) -> object:
    sub = await get_subscription(db, account_id)
    return get_plan_limits(sub)


async def require_feature(
    db: AsyncSession, account_id: uuid.UUID, feature: str
) -> None:
    """Raise PaymentRequiredError if the account's plan lacks the named feature."""
    sub = await get_subscription(db, account_id)
    effective = get_effective_plan(sub)
    if effective is None:
        raise PaymentRequiredError(
            "Your trial has expired or your subscription is inactive. Please upgrade."
        )
    limits = PLAN_LIMITS.get(effective)
    if limits is None or not getattr(limits, feature, False):
        raise PaymentRequiredError(
            "Your current plan does not include this feature. "
            "Upgrade to Agency or Enterprise to continue."
        )


async def check_limit(
    db: AsyncSession, account_id: uuid.UUID, limit_field: str, current_count: int
) -> None:
    """Raise PaymentRequiredError if current_count meets or exceeds the plan limit."""
    sub = await get_subscription(db, account_id)
    effective = get_effective_plan(sub)
    if effective is None:
        raise PaymentRequiredError("Subscription inactive. Please upgrade.")
    limits = PLAN_LIMITS.get(effective)
    if limits is None:
        return
    cap = getattr(limits, limit_field, None)
    if cap is not None and current_count >= cap:
        raise PaymentRequiredError(
            f"You have reached the {limit_field.replace('_', ' ')} limit for your plan. "
            "Please upgrade to continue."
        )


# ---------------------------------------------------------------------------
# Trial provisioning (called by account_service on every new account)
# ---------------------------------------------------------------------------

async def provision_trial(db: AsyncSession, account_id: uuid.UUID) -> Subscription:
    """Create a 14-day trial subscription for a newly created account."""
    sub = Subscription(
        account_id=account_id,
        plan=PlanName.trial,
        status=SubscriptionStatus.trialing,
        trial_ends_at=utcnow() + timedelta(days=settings.trial_days),
    )
    db.add(sub)
    await db.flush()
    logger.info("Provisioned %d-day trial for account %s", settings.trial_days, account_id)
    return sub


# ---------------------------------------------------------------------------
# Stripe checkout + portal
# ---------------------------------------------------------------------------

async def create_checkout_session(
    db: AsyncSession,
    account_id: uuid.UUID,
    user: AdminUser,
    plan: str,
    interval: str,
) -> str:
    """Create a Stripe Checkout session (subscription mode) and return its URL."""
    s = _stripe()
    pid = _price_id(plan, interval)
    if not pid:
        raise RevOSError(
            f"Stripe price ID for {plan}/{interval} is not configured. "
            "Set STRIPE_PRO_MONTHLY_PRICE_ID / STRIPE_AGENCY_MONTHLY_PRICE_ID etc.",
            status_code=503,
            code="stripe_unconfigured",
        )

    sub = await get_subscription(db, account_id)
    if sub is None:
        sub = await provision_trial(db, account_id)

    # Ensure the account has a Stripe customer.
    customer_id = sub.stripe_customer_id
    if not customer_id:
        customer = s.Customer.create(
            email=user.email,
            name=user.full_name or user.email,
            metadata={"account_id": str(account_id), "user_id": str(user.id)},
        )
        customer_id = customer["id"]
        sub.stripe_customer_id = customer_id
        db.add(sub)
        await db.flush()

    session = s.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": pid, "quantity": 1}],
        success_url=(
            f"{settings.frontend_base_url}/billing/success"
            "?session_id={CHECKOUT_SESSION_ID}"
        ),
        cancel_url=f"{settings.frontend_base_url}/billing",
        allow_promotion_codes=True,
        metadata={"account_id": str(account_id)},
    )
    return session["url"]


async def create_portal_session(
    db: AsyncSession, account_id: uuid.UUID
) -> str:
    """Create a Stripe Customer Portal session URL."""
    s = _stripe()
    sub = await get_subscription(db, account_id)
    if sub is None or not sub.stripe_customer_id:
        raise NotFoundError("No active Stripe customer for this account.")
    session = s.billing_portal.Session.create(
        customer=sub.stripe_customer_id,
        return_url=f"{settings.frontend_base_url}/billing",
    )
    return session["url"]


# ---------------------------------------------------------------------------
# Webhook handlers (called by billing router after signature verification)
# ---------------------------------------------------------------------------

async def handle_checkout_completed(db: AsyncSession, session_obj: dict) -> bool:
    """Process checkout.session.completed → activate subscription."""
    metadata = session_obj.get("metadata") or {}
    account_id_str = metadata.get("account_id")
    stripe_sub_id = session_obj.get("subscription")
    customer_id = session_obj.get("customer")

    if not account_id_str or not stripe_sub_id:
        return False

    try:
        account_id = uuid.UUID(account_id_str)
    except ValueError:
        return False

    sub = await get_subscription(db, account_id)
    if sub is None:
        return False

    # Fetch the Stripe subscription to get price + period details.
    s = _stripe()
    stripe_sub = s.Subscription.retrieve(stripe_sub_id)
    item = stripe_sub["items"]["data"][0]
    pid = item["price"]["id"]
    period_end_ts = stripe_sub.get("current_period_end")

    from datetime import datetime
    sub.plan = _plan_from_price_id(pid)
    sub.status = SubscriptionStatus.active
    sub.stripe_subscription_id = stripe_sub_id
    sub.stripe_customer_id = customer_id or sub.stripe_customer_id
    sub.stripe_price_id = pid
    sub.billing_interval = _interval_from_price_id(pid)
    sub.current_period_end = (
        datetime.utcfromtimestamp(period_end_ts) if period_end_ts else None
    )
    db.add(sub)
    await db.flush()
    logger.info("Activated %s/%s subscription for account %s", sub.plan, sub.billing_interval, account_id)
    return True


async def handle_subscription_updated(db: AsyncSession, stripe_sub: dict) -> bool:
    """Process customer.subscription.updated → sync plan/status/period."""
    stripe_sub_id = stripe_sub.get("id")
    if not stripe_sub_id:
        return False

    res = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    )
    sub = res.scalar_one_or_none()
    if sub is None:
        return False

    stripe_status = stripe_sub.get("status", "")
    status_map = {
        "active": SubscriptionStatus.active,
        "past_due": SubscriptionStatus.past_due,
        "canceled": SubscriptionStatus.canceled,
        "incomplete": SubscriptionStatus.incomplete,
        "trialing": SubscriptionStatus.trialing,
    }
    sub.status = status_map.get(stripe_status, sub.status)

    items = (stripe_sub.get("items") or {}).get("data") or []
    if items:
        pid = items[0]["price"]["id"]
        sub.plan = _plan_from_price_id(pid)
        sub.stripe_price_id = pid
        sub.billing_interval = _interval_from_price_id(pid)

    period_end = stripe_sub.get("current_period_end")
    if period_end:
        from datetime import datetime
        sub.current_period_end = datetime.utcfromtimestamp(period_end)

    db.add(sub)
    await db.flush()
    return True


async def handle_subscription_deleted(db: AsyncSession, stripe_sub: dict) -> bool:
    """Process customer.subscription.deleted → cancel locally."""
    stripe_sub_id = stripe_sub.get("id")
    if not stripe_sub_id:
        return False

    res = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    )
    sub = res.scalar_one_or_none()
    if sub is None:
        return False

    sub.status = SubscriptionStatus.canceled
    sub.canceled_at = utcnow()
    db.add(sub)
    await db.flush()
    logger.info("Canceled subscription for account %s", sub.account_id)
    return True
