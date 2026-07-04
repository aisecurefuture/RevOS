"""Automation router — auto-approve autopilot (P3-M7).

Owner-only. Turning auto-approve on disables the human review gate for the
account until an optional expiry, so it is deliberately the highest-privilege
setting.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Request

from app.core.audit import write_audit
from app.core.exceptions import NotFoundError, RevOSError
from app.deps import DbSession, require_owner, verify_csrf
from app.models.account import Account
from app.models.base import utcnow
from app.models.user import AdminUser
from app.schemas.automation import AutoApproveRequest, AutoApproveStatus

router = APIRouter(prefix="/automation", tags=["automation"])


def _account_id(request: Request) -> uuid.UUID:
    acc = getattr(request.state, "account_id", None)
    if acc is None:
        raise RevOSError("No active account.", code="no_account", status_code=400)
    return acc


def _status(acct: Account) -> AutoApproveStatus:
    active = acct.auto_approve_enabled and (
        acct.auto_approve_until is None or acct.auto_approve_until > utcnow()
    )
    return AutoApproveStatus(
        enabled=active,
        until=acct.auto_approve_until if active else None,
        indefinite=active and acct.auto_approve_until is None,
    )


@router.get("/auto-approve", response_model=AutoApproveStatus)
async def get_auto_approve(
    request: Request,
    db: DbSession,
    user: AdminUser = Depends(require_owner),
) -> AutoApproveStatus:
    acct = await db.get(Account, _account_id(request))
    if acct is None:
        raise NotFoundError("Account not found.")
    return _status(acct)


@router.post("/auto-approve", response_model=AutoApproveStatus)
async def set_auto_approve(
    body: AutoApproveRequest,
    request: Request,
    db: DbSession,
    user: AdminUser = Depends(require_owner),
    _: None = Depends(verify_csrf),
) -> AutoApproveStatus:
    acct = await db.get(Account, _account_id(request))
    if acct is None:
        raise NotFoundError("Account not found.")

    if body.enabled:
        acct.auto_approve_enabled = True
        acct.auto_approve_until = (
            utcnow() + timedelta(hours=body.duration_hours) if body.duration_hours else None
        )
        acct.auto_approve_set_by = user.id
    else:
        acct.auto_approve_enabled = False
        acct.auto_approve_until = None

    db.add(acct)
    await db.flush()
    await write_audit(
        db, action="automation.auto_approve.set", user_id=user.id,
        entity_type="account", entity_id=str(acct.id), request=request,
        meta={"enabled": body.enabled, "duration_hours": body.duration_hours},
    )
    return _status(acct)
