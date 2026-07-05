"""Per-account low-cost integration credentials (Phase 3).

Admin+ manage credentials (paste API keys, save config). Actions that push
data out (shorten, push-contacts) require editor+ — the same bar as other
content-affecting operations.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.config import settings
from app.core.exceptions import NotFoundError, RevOSError
from app.deps import DbSession, require_admin, require_editor, verify_csrf
from app.models.integration_credential import IntegrationCredential, IntegrationProvider
from app.models.user import AdminUser
from app.schemas.integration_credential import (
    BitlyRequest,
    CalendlyRequest,
    GoogleSheetsRequest,
    IntegrationCredentialOut,
    NotionRequest,
    PushContactsOut,
    ShortenOut,
    ShortenRequest,
    ZapierRequest,
    ZapierSaveOut,
)
from app.services import crm_service, integration_credentials_service as svc
from app.services.integrations import bitly as bitly_client
from app.services.integrations import google_sheets as sheets_client
from app.services.integrations import notion as notion_client

router = APIRouter(prefix="/integrations", tags=["integration-credentials"])

_NOTION_PUSH_LIMIT = 100      # Notion's REST API is one page per request
_SHEETS_PUSH_LIMIT = 500      # Sheets append is a single batched call


def _account_id(request: Request) -> uuid.UUID:
    acc = getattr(request.state, "account_id", None)
    if acc is None:
        raise RevOSError("No active account.", code="no_account", status_code=400)
    return acc


def _out(cred: IntegrationCredential) -> IntegrationCredentialOut:
    return IntegrationCredentialOut(provider=cred.provider, config=cred.config, status=cred.status)


@router.get("/credentials", response_model=list[IntegrationCredentialOut])
async def list_credentials(
    request: Request, db: DbSession, _user: AdminUser = Depends(require_admin),
) -> list[IntegrationCredentialOut]:
    creds = await svc.list_credentials(db, _account_id(request))
    return [_out(c) for c in creds]


@router.post("/credentials/calendly", response_model=IntegrationCredentialOut)
async def save_calendly(
    body: CalendlyRequest, request: Request, db: DbSession,
    user: AdminUser = Depends(require_admin), _: None = Depends(verify_csrf),
) -> IntegrationCredentialOut:
    cred = await svc.save_calendly(db, _account_id(request), body.scheduling_url, user)
    return _out(cred)


@router.post("/credentials/notion", response_model=IntegrationCredentialOut)
async def save_notion(
    body: NotionRequest, request: Request, db: DbSession,
    user: AdminUser = Depends(require_admin), _: None = Depends(verify_csrf),
) -> IntegrationCredentialOut:
    cred = await svc.save_notion(db, _account_id(request), body.api_key, body.database_id, user)
    return _out(cred)


@router.post("/credentials/bitly", response_model=IntegrationCredentialOut)
async def save_bitly(
    body: BitlyRequest, request: Request, db: DbSession,
    user: AdminUser = Depends(require_admin), _: None = Depends(verify_csrf),
) -> IntegrationCredentialOut:
    cred = await svc.save_bitly(db, _account_id(request), body.access_token, user)
    return _out(cred)


@router.post("/credentials/google-sheets", response_model=IntegrationCredentialOut)
async def save_google_sheets(
    body: GoogleSheetsRequest, request: Request, db: DbSession,
    user: AdminUser = Depends(require_admin), _: None = Depends(verify_csrf),
) -> IntegrationCredentialOut:
    cred = await svc.save_google_sheets(
        db, _account_id(request), body.service_account_json, body.spreadsheet_id, user,
    )
    return _out(cred)


@router.post("/credentials/zapier", response_model=ZapierSaveOut)
async def save_zapier(
    body: ZapierRequest, request: Request, db: DbSession,
    user: AdminUser = Depends(require_admin), _: None = Depends(verify_csrf),
) -> ZapierSaveOut:
    account_id = _account_id(request)
    cred, new_secret = await svc.save_zapier(db, account_id, body.outbound_webhook_url, user)
    return ZapierSaveOut(
        credential=_out(cred),
        inbound_webhook_url=f"{settings.public_base_url}/api/integrations/inbound/contact/{account_id}",
        inbound_secret=new_secret,
    )


@router.post("/credentials/zapier/regenerate-secret")
async def regenerate_zapier_secret(
    request: Request, db: DbSession,
    user: AdminUser = Depends(require_admin), _: None = Depends(verify_csrf),
) -> dict:
    """Rotate the inbound signing secret. The old value stops working immediately
    — update your Zapier trigger with the new one before saving."""
    new_secret = await svc.regenerate_zapier_secret(db, _account_id(request), user)
    return {"inbound_secret": new_secret}


@router.delete("/credentials/{provider}", status_code=204)
async def delete_credential(
    provider: IntegrationProvider, request: Request, db: DbSession,
    user: AdminUser = Depends(require_admin), _: None = Depends(verify_csrf),
) -> Response:
    await svc.delete_credential(db, _account_id(request), provider)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

@router.post("/bitly/shorten", response_model=ShortenOut)
async def shorten_link(
    body: ShortenRequest, request: Request, db: DbSession,
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> ShortenOut:
    cred = await svc.get_credential(db, _account_id(request), IntegrationProvider.bitly)
    if cred is None:
        raise NotFoundError("Connect Bitly in Settings → Integrations first.")
    secret = await svc.get_secret_data(cred)
    if secret is None:
        raise RevOSError("Bitly token not found in secrets store.", code="token_missing", status_code=503)
    short_url = await bitly_client.shorten(secret["access_token"], body.url)
    return ShortenOut(short_url=short_url)


@router.post("/notion/push-contacts", response_model=PushContactsOut)
async def push_contacts_to_notion(
    request: Request, db: DbSession,
    brand_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=_NOTION_PUSH_LIMIT),
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> PushContactsOut:
    cred = await svc.get_credential(db, _account_id(request), IntegrationProvider.notion)
    if cred is None:
        raise NotFoundError("Connect Notion in Settings → Integrations first.")
    secret = await svc.get_secret_data(cred)
    if secret is None:
        raise RevOSError("Notion API key not found in secrets store.", code="token_missing", status_code=503)

    api_key = secret["api_key"]
    database_id = cred.config["database_id"]
    schema = await notion_client.get_database_schema(api_key, database_id)

    contacts = await crm_service.list_contacts(db, brand_id=brand_id, limit=limit)
    pushed = 0
    for c in contacts:
        await notion_client.create_page(api_key, database_id, schema, {
            "first_name": c.first_name, "last_name": c.last_name, "email": c.email,
            "phone": c.phone, "title": c.title, "source": c.source, "lead_score": c.lead_score,
        })
        pushed += 1
    return PushContactsOut(pushed=pushed)


@router.post("/google-sheets/push-contacts", response_model=PushContactsOut)
async def push_contacts_to_sheets(
    request: Request, db: DbSession,
    brand_id: uuid.UUID | None = None,
    limit: int = Query(200, ge=1, le=_SHEETS_PUSH_LIMIT),
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> PushContactsOut:
    cred = await svc.get_credential(db, _account_id(request), IntegrationProvider.google_sheets)
    if cred is None:
        raise NotFoundError("Connect Google Sheets in Settings → Integrations first.")
    secret = await svc.get_secret_data(cred)
    if secret is None:
        raise RevOSError("Service-account credentials not found in secrets store.", code="token_missing", status_code=503)

    service_account = sheets_client.parse_service_account(secret["service_account_json"])
    access_token = await sheets_client.get_access_token(service_account)

    contacts = await crm_service.list_contacts(db, brand_id=brand_id, limit=limit)
    rows = [
        [c.first_name or "", c.last_name or "", c.email or "", c.title or "",
         c.source or "", c.lead_score]
        for c in contacts
    ]
    if not rows:
        return PushContactsOut(pushed=0)
    pushed = await sheets_client.append_rows(access_token, cred.config["spreadsheet_id"], rows)
    return PushContactsOut(pushed=pushed)
