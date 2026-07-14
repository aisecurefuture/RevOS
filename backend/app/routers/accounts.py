"""Accounts (workspaces) + membership management (Phase 2 M2).

A user sees the accounts they belong to, can create team workspaces, switch the
active account (re-issuing the session with a new tenant scope), and — as an
admin of an account — view members, send invitations, and manage roles.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import Response as PlainResponse

from app.core.exceptions import PermissionError_
from app.core.rbac import role_at_least
from app.core.security import generate_csrf_token
from app.deps import CurrentUser, DbSession, require_verified_email, verify_csrf
from app.models.user import AdminUser, Role
from app.routers.auth import _set_auth_cookies
from app.schemas.account import (
    AccountOut,
    AcceptInvitationRequest,
    CreateTeamRequest,
    InvitationCreatedOut,
    InvitationOut,
    InviteRequest,
    MemberOut,
    MembershipOut,
    ResetMemberPasswordOut,
    ResetMemberPasswordRequest,
    SwitchAccountRequest,
    UpdateMemberRoleRequest,
)
from app.core.audit import write_audit
from app.services import account_service, invitation_service

router = APIRouter(prefix="/accounts", tags=["accounts"])


async def _member_or_403(db, user: AdminUser, account_id: uuid.UUID):
    membership = await account_service.get_membership(db, user.id, account_id)
    if membership is None:
        raise PermissionError_("You are not a member of this account.", code="not_a_member")
    return membership


async def _admin_of(db, user: AdminUser, account_id: uuid.UUID):
    """Membership that is admin or above, or 403."""
    membership = await account_service.get_membership(db, user.id, account_id)
    if membership is None or not role_at_least(membership.role, Role.admin):
        raise PermissionError_("Admin access required for this account.", code="insufficient_role")
    return membership


async def _owner_of(db, user: AdminUser, account_id: uuid.UUID):
    """Membership that is owner, or 403."""
    membership = await account_service.get_membership(db, user.id, account_id)
    if membership is None or not role_at_least(membership.role, Role.owner):
        raise PermissionError_("Owner access required for this account.", code="insufficient_role")
    return membership


@router.get("", response_model=list[MembershipOut])
async def my_accounts(request: Request, user: CurrentUser, db: DbSession) -> list[MembershipOut]:
    active = getattr(request.state, "account_id", None)
    pairs = await account_service.accounts_for_user(db, user.id)
    return [
        MembershipOut(
            account=AccountOut.model_validate(acct), role=role,
            is_active=(acct.id == active),
        )
        for acct, role in pairs
    ]


@router.post("", response_model=AccountOut, status_code=201)
async def create_team(
    body: CreateTeamRequest, user: CurrentUser, db: DbSession,
    _c: None = Depends(verify_csrf),
) -> AccountOut:
    account = await account_service.create_team_account(db, user, body.name)
    return AccountOut.model_validate(account)


@router.post("/switch")
async def switch_account(
    body: SwitchAccountRequest, response: Response, user: CurrentUser, db: DbSession,
    _c: None = Depends(verify_csrf),
) -> dict:
    """Re-issue the session scoped to another of the user's accounts."""
    membership = await _member_or_403(db, user, body.account_id)
    csrf = generate_csrf_token()
    _set_auth_cookies(
        response, user, csrf, active_account=str(body.account_id), role=membership.role
    )
    return {"account_id": str(body.account_id), "role": membership.role, "csrf_token": csrf}


@router.get("/{account_id}/members", response_model=list[MemberOut])
async def list_members(
    account_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> list[MemberOut]:
    await _member_or_403(db, user, account_id)
    members = await account_service.list_members(db, account_id)
    return [
        MemberOut(user_id=u.id, email=u.email, full_name=u.full_name, role=role)
        for u, role in members
    ]


@router.patch("/{account_id}/members/{member_user_id}", response_model=MemberOut)
async def change_member_role(
    account_id: uuid.UUID,
    member_user_id: uuid.UUID,
    body: UpdateMemberRoleRequest,
    user: CurrentUser,
    db: DbSession,
    _c: None = Depends(verify_csrf),
) -> MemberOut:
    requester = await _owner_of(db, user, account_id)
    try:
        new_role = Role(body.role)
    except ValueError:
        raise PermissionError_(f"Invalid role: {body.role}")
    membership = await account_service.change_member_role(
        db, account_id, member_user_id, new_role, requester
    )
    # Load user for the response
    members = await account_service.list_members(db, account_id)
    for u, role in members:
        if u.id == member_user_id:
            return MemberOut(user_id=u.id, email=u.email, full_name=u.full_name, role=role)
    return MemberOut(
        user_id=member_user_id,
        email="",
        full_name="",
        role=membership.role,
    )


@router.post("/{account_id}/members/{member_user_id}/reset-password",
             response_model=ResetMemberPasswordOut)
async def reset_member_password(
    account_id: uuid.UUID,
    member_user_id: uuid.UUID,
    body: ResetMemberPasswordRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _c: None = Depends(verify_csrf),
) -> ResetMemberPasswordOut:
    """Admin/owner resets another member's password (link or temp password)."""
    requester = await _admin_of(db, user, account_id)
    result = await account_service.admin_reset_member_password(
        db, account_id, member_user_id, requester, mode=body.mode,
    )
    await write_audit(
        db, action="account.member_password_reset", user_id=user.id,
        entity_type="admin_user", entity_id=str(member_user_id), request=request,
        meta={"mode": body.mode},
    )
    return ResetMemberPasswordOut(**result)


@router.delete("/{account_id}/members/{member_user_id}", status_code=204, response_class=PlainResponse)
async def remove_member(
    account_id: uuid.UUID,
    member_user_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    _c: None = Depends(verify_csrf),
) -> PlainResponse:
    requester = await _owner_of(db, user, account_id)
    await account_service.remove_member(db, account_id, member_user_id, requester)
    return PlainResponse(status_code=204)


# --- Invitations ------------------------------------------------------------

@router.post("/{account_id}/invitations", response_model=InvitationCreatedOut, status_code=201)
async def invite_member(
    account_id: uuid.UUID,
    body: InviteRequest,
    user: CurrentUser,
    db: DbSession,
    _c: None = Depends(verify_csrf),
    _verified: AdminUser = Depends(require_verified_email),
) -> InvitationCreatedOut:
    await _admin_of(db, user, account_id)
    from app.config import settings as cfg
    invite, token = await invitation_service.send_invitation(
        db, account_id, user, body.email, body.role
    )
    accept_url = f"{cfg.frontend_base_url}/join?token={token}"
    return InvitationCreatedOut(
        id=invite.id,
        email=invite.email,
        role=invite.role,
        created_at=invite.created_at,
        token=token,
        accept_url=accept_url,
    )


@router.get("/{account_id}/invitations", response_model=list[InvitationOut])
async def list_invitations(
    account_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> list[InvitationOut]:
    await _admin_of(db, user, account_id)
    invites = await invitation_service.list_pending_invitations(db, account_id)
    return [InvitationOut.model_validate(i) for i in invites]


@router.post("/{account_id}/invitations/{invite_id}/resend", response_model=InvitationCreatedOut)
async def resend_invitation(
    account_id: uuid.UUID,
    invite_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    _c: None = Depends(verify_csrf),
    _verified: AdminUser = Depends(require_verified_email),
) -> InvitationCreatedOut:
    await _admin_of(db, user, account_id)
    from app.config import settings as cfg
    invite, token = await invitation_service.resend_invitation(db, invite_id, account_id, user)
    return InvitationCreatedOut(
        id=invite.id, email=invite.email, role=invite.role, created_at=invite.created_at,
        token=token, accept_url=f"{cfg.frontend_base_url}/join?token={token}",
    )


@router.delete("/{account_id}/invitations/{invite_id}", status_code=204, response_class=PlainResponse)
async def revoke_invitation(
    account_id: uuid.UUID,
    invite_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    _c: None = Depends(verify_csrf),
) -> PlainResponse:
    await _admin_of(db, user, account_id)
    await invitation_service.revoke_invitation(db, invite_id, account_id)
    return PlainResponse(status_code=204)
