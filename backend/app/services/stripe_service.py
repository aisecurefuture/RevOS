"""Stripe integration: checkout links + signed webhook → revenue.

Webhook signatures are verified manually (HMAC-SHA256 over ``{t}.{payload}``)
so the verify path has no hard dependency on the Stripe SDK and is unit-testable
without network access. Degrades gracefully when Stripe is not configured.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.analytics import RevenueStatus
from app.models.offer import Offer
from app.services import revenue_service

_TOLERANCE = 5 * 60


def checkout_link(offer: Offer) -> str | None:
    """Return a Stripe checkout URL for an offer, or None if unavailable.

    Prefers a pre-built payment link; otherwise creates a Checkout Session when
    Stripe is configured and the offer has a price id."""
    if offer.stripe_payment_link:
        return offer.stripe_payment_link
    if settings.stripe_secret_key and offer.stripe_price_id:
        import stripe

        stripe.api_key = settings.stripe_secret_key
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": offer.stripe_price_id, "quantity": 1}],
            success_url=f"{settings.public_base_url}/thank-you",
            cancel_url=f"{settings.public_base_url}/",
            metadata={"brand_id": str(offer.brand_id), "offer_id": str(offer.id)},
        )
        return session.url
    return None


def verify_webhook(payload: bytes, signature_header: str) -> bool:
    secret = settings.stripe_webhook_secret
    if not secret or not signature_header:
        return False
    parts = dict(p.split("=", 1) for p in signature_header.split(",") if "=" in p)
    timestamp, sig = parts.get("t"), parts.get("v1")
    if not (timestamp and sig):
        return False
    try:
        if abs(time.time() - int(timestamp)) > _TOLERANCE:
            return False
    except ValueError:
        return False
    signed = f"{timestamp}.".encode() + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


async def handle_event(db: AsyncSession, event: dict) -> bool:
    """Record revenue from a completed checkout / successful payment."""
    event_type = event.get("type", "")
    if event_type not in ("checkout.session.completed", "payment_intent.succeeded"):
        return False
    obj = event.get("data", {}).get("object", {}) or {}
    amount = obj.get("amount_total") or obj.get("amount") or obj.get("amount_received")
    metadata = obj.get("metadata", {}) or {}
    brand_id = metadata.get("brand_id")
    if not (amount and brand_id):
        return False
    await revenue_service.record_revenue(db, {
        "brand_id": uuid.UUID(brand_id),
        "offer_id": uuid.UUID(metadata["offer_id"]) if metadata.get("offer_id") else None,
        "amount_cents": int(amount),
        "currency": (obj.get("currency") or "usd").upper(),
        "source": "stripe",
        "status": RevenueStatus.paid,
        "stripe_object_id": obj.get("id"),
    })
    return True
