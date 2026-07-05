"""Integration endpoints: status, exports, inbound webhooks, checkout links."""

from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse

from app.core.exceptions import AuthError, NotFoundError, RevOSError
from app.core.rate_limit import rate_limit
from app.deps import DbSession, require_admin, require_authenticated
from app.models.user import AdminUser
from app.services import (
    integration_credentials_service,
    integrations_service,
    offer_service,
    stripe_service,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])

_inbound_limit = rate_limit("inbound_webhook", "60/minute")


@router.get("/status")
async def status(_user: Annotated[AdminUser, Depends(require_admin)]) -> dict:
    return integrations_service.integration_status()


@router.get("/export", response_class=PlainTextResponse)
async def export(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    entity: str = Query("contacts"),
    fmt: str = Query("csv", pattern="^(csv|notion)$"),
    brand_id: uuid.UUID | None = None,
) -> PlainTextResponse:
    if entity != "contacts":
        raise RevOSError("Only 'contacts' export is supported here.")
    content, media_type = await integrations_service.export_contacts(db, brand_id=brand_id, fmt=fmt)
    ext = "md" if fmt == "notion" else "csv"
    return PlainTextResponse(
        content, media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename=contacts.{ext}"})


@router.post("/inbound/contact/{account_id}")
async def inbound_contact(
    account_id: uuid.UUID, request: Request, db: DbSession, _rl: None = Depends(_inbound_limit)
) -> dict:
    """Zapier/Make inbound: create a CRM contact. HMAC-signed (X-Signature) with
    the account's own inbound secret, generated when Zapier is configured under
    Settings → Integrations."""
    raw = await request.body()
    secret = await integration_credentials_service.get_zapier_inbound_secret(db, account_id)
    if not integrations_service.verify_inbound_signature(
        raw, request.headers.get("x-signature"), request.headers.get("x-timestamp"), secret,
    ):
        raise AuthError("Invalid or expired webhook signature.")
    try:
        data = json.loads(raw.decode())
    except (ValueError, UnicodeDecodeError) as exc:
        raise RevOSError("Malformed payload.") from exc
    return await integrations_service.handle_inbound_contact(db, account_id, data)


@router.get("/checkout/{offer_id}")
async def checkout(
    offer_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> dict:
    offer = await offer_service.get_offer_or_404(db, offer_id)
    url = stripe_service.checkout_link(offer)
    if url is None:
        raise NotFoundError("No checkout link available for this offer.")
    return {"url": url}
