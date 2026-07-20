"""Platform super-admin console (/admin). Gated by the PLATFORM_ADMIN_EMAILS
allowlist via require_platform_admin — cross-tenant operations."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from app.core.audit import write_audit
from app.deps import DbSession, require_platform_admin, verify_csrf
from app.models.user import AdminUser
from app.schemas.platform_admin import (
    AdminAccountOut,
    AdminUserOut,
    CompAccessRequest,
    CreateTenantOut,
    CreateTenantRequest,
    DisableAccountRequest,
)
from app.services import platform_admin_service as svc

router = APIRouter(prefix="/admin", tags=["platform-admin"])


@router.get("/accounts", response_model=list[AdminAccountOut])
async def list_accounts(
    db: DbSession, _admin: AdminUser = Depends(require_platform_admin),
) -> list[AdminAccountOut]:
    return [AdminAccountOut(**a) for a in await svc.list_accounts(db)]


@router.post("/accounts", response_model=CreateTenantOut, status_code=201)
async def create_tenant(
    body: CreateTenantRequest, request: Request, db: DbSession,
    admin: AdminUser = Depends(require_platform_admin), _c: None = Depends(verify_csrf),
) -> CreateTenantOut:
    result = await svc.create_tenant(
        db, admin, name=body.name, lead_email=body.lead_email, lead_name=body.lead_name or "",
    )
    await write_audit(db, action="admin.tenant_create", user_id=admin.id,
                      entity_type="account", entity_id=str(result["account_id"]), request=request,
                      meta={"lead_email": body.lead_email})
    return CreateTenantOut(**result)


@router.post("/accounts/{account_id}/disable", response_model=AdminAccountOut)
async def disable_account(
    account_id: uuid.UUID, body: DisableAccountRequest, request: Request, db: DbSession,
    admin: AdminUser = Depends(require_platform_admin), _c: None = Depends(verify_csrf),
) -> AdminAccountOut:
    await svc.set_account_disabled(db, account_id, admin, disabled=True, reason=body.reason)
    await write_audit(db, action="admin.account_disable", user_id=admin.id,
                      entity_type="account", entity_id=str(account_id), request=request,
                      meta={"reason": body.reason})
    return await _account_out(db, account_id)


@router.post("/accounts/{account_id}/enable", response_model=AdminAccountOut)
async def enable_account(
    account_id: uuid.UUID, request: Request, db: DbSession,
    admin: AdminUser = Depends(require_platform_admin), _c: None = Depends(verify_csrf),
) -> AdminAccountOut:
    await svc.set_account_disabled(db, account_id, admin, disabled=False)
    await write_audit(db, action="admin.account_enable", user_id=admin.id,
                      entity_type="account", entity_id=str(account_id), request=request)
    return await _account_out(db, account_id)


@router.post("/accounts/{account_id}/comp", response_model=AdminAccountOut)
async def set_comp_access(
    account_id: uuid.UUID, body: CompAccessRequest, request: Request, db: DbSession,
    admin: AdminUser = Depends(require_platform_admin), _c: None = Depends(verify_csrf),
) -> AdminAccountOut:
    """Grant/revoke complimentary access — the account bypasses the trial
    paywall entirely (plan=comp, active, no expiry). For the internal team."""
    await svc.set_account_comp(db, account_id, enabled=body.enabled)
    await write_audit(db, action="admin.account_comp", user_id=admin.id,
                      entity_type="account", entity_id=str(account_id), request=request,
                      meta={"enabled": body.enabled})
    return await _account_out(db, account_id)


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    db: DbSession, _admin: AdminUser = Depends(require_platform_admin),
) -> list[AdminUserOut]:
    return [AdminUserOut(**u) for u in await svc.list_users(db)]


@router.post("/users/{user_id}/disable", status_code=200)
async def disable_user(
    user_id: uuid.UUID, request: Request, db: DbSession,
    admin: AdminUser = Depends(require_platform_admin), _c: None = Depends(verify_csrf),
) -> dict:
    await svc.set_user_active(db, user_id, active=False)
    await write_audit(db, action="admin.user_disable", user_id=admin.id,
                      entity_type="admin_user", entity_id=str(user_id), request=request)
    return {"status": "disabled"}


@router.post("/users/{user_id}/enable", status_code=200)
async def enable_user(
    user_id: uuid.UUID, request: Request, db: DbSession,
    admin: AdminUser = Depends(require_platform_admin), _c: None = Depends(verify_csrf),
) -> dict:
    await svc.set_user_active(db, user_id, active=True)
    await write_audit(db, action="admin.user_enable", user_id=admin.id,
                      entity_type="admin_user", entity_id=str(user_id), request=request)
    return {"status": "enabled"}


@router.post("/users/{user_id}/unlock", status_code=200)
async def unlock_user(
    user_id: uuid.UUID, request: Request, db: DbSession,
    admin: AdminUser = Depends(require_platform_admin), _c: None = Depends(verify_csrf),
) -> dict:
    await svc.unlock_user(db, user_id)
    await write_audit(db, action="admin.user_unlock", user_id=admin.id,
                      entity_type="admin_user", entity_id=str(user_id), request=request)
    return {"status": "unlocked"}


async def _account_out(db, account_id: uuid.UUID) -> AdminAccountOut:
    for a in await svc.list_accounts(db):
        if a["id"] == account_id:
            return AdminAccountOut(**a)
    from app.core.exceptions import NotFoundError
    raise NotFoundError("Account not found.")
