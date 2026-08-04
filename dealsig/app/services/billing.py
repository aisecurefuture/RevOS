from __future__ import annotations

import stripe
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User, WebhookEvent

ACTIVE_STATUSES = {"active", "trialing"}


class BillingNotConfigured(RuntimeError):
    pass


def _configure() -> None:
    settings = get_settings()
    if not settings.stripe_secret_key or not settings.stripe_price_id:
        raise BillingNotConfigured("Stripe test credentials and STRIPE_PRICE_ID are not configured")
    stripe.api_key = settings.stripe_secret_key


def create_checkout_url(user: User) -> str:
    _configure()
    settings = get_settings()
    params: dict = {
        "mode": "subscription",
        "line_items": [{"price": settings.stripe_price_id, "quantity": 1}],
        "success_url": f"{settings.base_url}/billing?checkout=success",
        "cancel_url": f"{settings.base_url}/billing?checkout=cancelled",
        "client_reference_id": str(user.id),
        "subscription_data": {"metadata": {"dealsig_user_id": str(user.id)}},
        "allow_promotion_codes": True,
    }
    if user.stripe_customer_id:
        params["customer"] = user.stripe_customer_id
    else:
        params["customer_email"] = user.email
    session = stripe.checkout.Session.create(**params)
    if not session.url:
        raise RuntimeError("Stripe did not return a Checkout URL")
    return str(session.url)


def create_portal_url(user: User) -> str:
    _configure()
    if not user.stripe_customer_id:
        raise BillingNotConfigured("No Stripe customer is associated with this account yet")
    settings = get_settings()
    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=f"{settings.base_url}/billing",
    )
    return str(session.url)


def construct_webhook(payload: bytes, signature: str):
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise BillingNotConfigured("STRIPE_WEBHOOK_SECRET is not configured")
    return stripe.Webhook.construct_event(payload, signature, settings.stripe_webhook_secret)


def _value(obj, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def process_event(db: Session, event) -> bool:
    event_id = str(_value(event, "id"))
    if db.get(WebhookEvent, event_id):
        return False
    event_type = str(_value(event, "type"))
    data = _value(event, "data", {})
    obj = _value(data, "object", {})

    user: User | None = None
    if event_type == "checkout.session.completed":
        reference = _value(obj, "client_reference_id")
        if reference and str(reference).isdigit():
            user = db.get(User, int(reference))
        if user:
            user.stripe_customer_id = str(_value(obj, "customer") or "") or None
            user.stripe_subscription_id = str(_value(obj, "subscription") or "") or None
            # Checkout completion is not always proof of an active asynchronous payment.
            payment_status = str(_value(obj, "payment_status", ""))
            if payment_status in {"paid", "no_payment_required"}:
                user.subscription_status = "active"
    elif event_type in {"customer.subscription.created", "customer.subscription.updated"}:
        customer_id = str(_value(obj, "customer") or "")
        user = db.scalar(select(User).where(User.stripe_customer_id == customer_id))
        if not user:
            metadata = _value(obj, "metadata", {}) or {}
            user_id = _value(metadata, "dealsig_user_id")
            if user_id and str(user_id).isdigit():
                user = db.get(User, int(user_id))
        if user:
            user.stripe_customer_id = customer_id
            user.stripe_subscription_id = str(_value(obj, "id"))
            user.subscription_status = str(_value(obj, "status", "inactive"))
    elif event_type == "customer.subscription.deleted":
        subscription_id = str(_value(obj, "id"))
        user = db.scalar(
            select(User).where(User.stripe_subscription_id == subscription_id)
        )
        if user:
            user.subscription_status = "canceled"
    elif event_type == "invoice.payment_failed":
        customer_id = str(_value(obj, "customer") or "")
        user = db.scalar(select(User).where(User.stripe_customer_id == customer_id))
        if user:
            user.subscription_status = "past_due"

    db.add(WebhookEvent(event_id=event_id, event_type=event_type))
    db.commit()
    return True

