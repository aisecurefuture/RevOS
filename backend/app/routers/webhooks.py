"""Inbound provider webhooks (Resend email status events).

The raw request body is verified against the Svix signature before any state
change. Unverified requests are rejected with 401.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request

from app.core.exceptions import AuthError
from app.core.rate_limit import rate_limit
from app.deps import DbSession
from app.services import stripe_service, webhook_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Sized to legitimate provider volume; blunts signature-brute-force / flooding.
_webhook_limit = rate_limit("provider_webhook", "240/minute")


@router.post("/resend")
async def resend_webhook(request: Request, db: DbSession,
                         _rl: None = Depends(_webhook_limit)) -> dict:
    raw = await request.body()
    svix_id, svix_ts, svix_sig = webhook_service.parse_signature_headers(request.headers)
    if not webhook_service.verify_signature(
        svix_id=svix_id, svix_timestamp=svix_ts, svix_signature=svix_sig, body=raw
    ):
        raise AuthError("Invalid webhook signature.")

    try:
        event = json.loads(raw.decode())
    except (ValueError, UnicodeDecodeError) as exc:
        raise AuthError("Malformed webhook payload.") from exc

    updated = await webhook_service.handle_event(db, event)
    return {"received": True, "updated": updated}


@router.post("/stripe")
async def stripe_webhook(request: Request, db: DbSession,
                         _rl: None = Depends(_webhook_limit)) -> dict:
    raw = await request.body()
    if not stripe_service.verify_webhook(raw, request.headers.get("stripe-signature", "")):
        raise AuthError("Invalid Stripe signature.")
    try:
        event = json.loads(raw.decode())
    except (ValueError, UnicodeDecodeError) as exc:
        raise AuthError("Malformed Stripe payload.") from exc
    recorded = await stripe_service.handle_event(db, event)
    return {"received": True, "revenue_recorded": recorded}
