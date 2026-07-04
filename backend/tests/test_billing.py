"""Phase 2 M3 — subscription provisioning, entitlements, billing status, webhooks."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.entitlements import get_effective_plan, is_trial_expired
from app.models.billing import PlanName, SubscriptionStatus
from app.models.base import utcnow


# --- helpers ----------------------------------------------------------------

async def _register(client, email, pw="PassWord1234"):
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": pw, "full_name": "Billing Test"},
    )
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


# --- provisioning tests (no Stripe) -----------------------------------------

@pytest.mark.asyncio
async def test_trial_created_on_register(api):
    """New account automatically gets a trial subscription."""
    h = await _register(api, "trial@billing.com")
    r = await api.get("/api/billing/status", headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["plan"] == "trial"
    assert data["status"] == "trialing"
    assert data["is_trial_expired"] is False
    assert data["effective_plan"] == "trial"


@pytest.mark.asyncio
async def test_trial_duration_is_14_days(api):
    """Trial ends_at should be ~14 days from now."""
    from datetime import datetime
    h = await _register(api, "duration@billing.com")
    r = await api.get("/api/billing/status", headers=h)
    data = r.json()
    ends = datetime.fromisoformat(data["trial_ends_at"])
    delta = ends - datetime.utcnow()
    # Allow ±1 minute around 14 days.
    assert timedelta(days=13, hours=23) < delta < timedelta(days=14, hours=1)


@pytest.mark.asyncio
async def test_billing_status_includes_limits(api):
    """Status endpoint returns plan limits shaped correctly."""
    h = await _register(api, "limits@billing.com")
    r = await api.get("/api/billing/status", headers=h)
    lim = r.json()["limits"]
    # Trial = agency-level: unlimited brands, api_access=True, client_workspaces=True
    assert lim["brands"] is None
    assert lim["api_access"] is True
    assert lim["client_workspaces"] is True
    assert lim["white_label"] is False


@pytest.mark.asyncio
async def test_billing_status_includes_prices(api):
    """Status endpoint always returns current display prices."""
    h = await _register(api, "prices@billing.com")
    r = await api.get("/api/billing/status", headers=h)
    prices = r.json()["prices"]
    assert prices["pro_monthly_cents"] == 14900
    assert prices["agency_monthly_cents"] == 44900
    assert prices["pro_annual_cents"] == 142800
    assert prices["agency_annual_cents"] == 430800


# --- entitlement unit tests (pure logic, no HTTP) ---------------------------

def test_expired_trial_returns_none():
    """get_effective_plan returns None when trial_ends_at is in the past."""
    from app.models.billing import Subscription
    sub = Subscription(
        account_id=__import__("uuid").uuid4(),
        plan=PlanName.trial,
        status=SubscriptionStatus.trialing,
        trial_ends_at=utcnow() - timedelta(days=1),
    )
    assert get_effective_plan(sub) is None
    assert is_trial_expired(sub) is True


def test_active_trial_returns_trial_plan():
    from app.models.billing import Subscription
    sub = Subscription(
        account_id=__import__("uuid").uuid4(),
        plan=PlanName.trial,
        status=SubscriptionStatus.trialing,
        trial_ends_at=utcnow() + timedelta(days=7),
    )
    assert get_effective_plan(sub) == PlanName.trial
    assert is_trial_expired(sub) is False


def test_active_pro_subscription_returns_pro():
    from app.models.billing import Subscription
    sub = Subscription(
        account_id=__import__("uuid").uuid4(),
        plan=PlanName.pro,
        status=SubscriptionStatus.active,
    )
    assert get_effective_plan(sub) == PlanName.pro


def test_canceled_returns_none():
    from app.models.billing import Subscription
    sub = Subscription(
        account_id=__import__("uuid").uuid4(),
        plan=PlanName.pro,
        status=SubscriptionStatus.canceled,
    )
    assert get_effective_plan(sub) is None


# --- webhook handler tests (feed fake event dicts directly) -----------------

@pytest.mark.asyncio
async def test_webhook_subscription_updated(api, async_session_factory):
    """handle_subscription_updated syncs status + plan from a Stripe event."""
    from app.services import billing_service

    h = await _register(api, "webhook@billing.com")

    # Get the account_id for this user
    r = await api.get("/api/accounts", headers=h)
    account_id = r.json()[0]["account"]["id"]

    # Manually set a stripe_subscription_id so the lookup works
    import uuid
    async with async_session_factory() as session:
        from sqlmodel import select
        from app.models.billing import Subscription
        res = await session.execute(
            select(Subscription).where(
                Subscription.account_id == uuid.UUID(account_id)
            )
        )
        sub = res.scalar_one()
        sub.stripe_subscription_id = "sub_test_123"
        sub.plan = PlanName.pro
        sub.status = SubscriptionStatus.active
        session.add(sub)
        await session.commit()

    # Feed a fake subscription.updated event
    fake_stripe_sub = {
        "id": "sub_test_123",
        "status": "past_due",
        "items": {
            "data": [{"price": {"id": "price_pro_monthly"}}]
        },
        "current_period_end": None,
    }

    async with async_session_factory() as session:
        handled = await billing_service.handle_subscription_updated(session, fake_stripe_sub)
        await session.commit()

    assert handled is True

    # Verify status updated
    async with async_session_factory() as session:
        from sqlmodel import select
        from app.models.billing import Subscription
        res = await session.execute(
            select(Subscription).where(
                Subscription.account_id == uuid.UUID(account_id)
            )
        )
        updated_sub = res.scalar_one()
        assert updated_sub.status == SubscriptionStatus.past_due


@pytest.mark.asyncio
async def test_webhook_subscription_deleted(api, async_session_factory):
    """handle_subscription_deleted marks subscription as canceled."""
    from app.services import billing_service

    h = await _register(api, "canceled@billing.com")
    r = await api.get("/api/accounts", headers=h)
    account_id = r.json()[0]["account"]["id"]

    import uuid
    async with async_session_factory() as session:
        from sqlmodel import select
        from app.models.billing import Subscription
        res = await session.execute(
            select(Subscription).where(
                Subscription.account_id == uuid.UUID(account_id)
            )
        )
        sub = res.scalar_one()
        sub.stripe_subscription_id = "sub_cancel_456"
        sub.status = SubscriptionStatus.active
        session.add(sub)
        await session.commit()

    async with async_session_factory() as session:
        handled = await billing_service.handle_subscription_deleted(
            session, {"id": "sub_cancel_456"}
        )
        await session.commit()

    assert handled is True

    async with async_session_factory() as session:
        from sqlmodel import select
        from app.models.billing import Subscription
        res = await session.execute(
            select(Subscription).where(
                Subscription.account_id == uuid.UUID(account_id)
            )
        )
        sub = res.scalar_one()
        assert sub.status == SubscriptionStatus.canceled
        assert sub.canceled_at is not None
