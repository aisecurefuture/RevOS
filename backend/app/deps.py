"""Shared FastAPI dependencies: DB session, current user, RBAC, CSRF."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthError, PermissionError_
from app.core.rbac import role_at_least
from app.core.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    CSRF_HEADER,
    csrf_tokens_match,
    decode_token,
)
from app.core.tenancy import set_active_account
from app.database import get_session
from app.models.user import AdminUser, Role
from app.services.account_service import resolve_active_membership

DbSession = Annotated[AsyncSession, Depends(get_session)]


def _parse_uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except (ValueError, TypeError):
        return None

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _extract_token(request: Request) -> str | None:
    """Prefer Authorization: Bearer (API clients); fall back to cookie (UI)."""
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(ACCESS_COOKIE)


async def get_current_user(request: Request, db: DbSession) -> AdminUser:
    token = _extract_token(request)
    if not token:
        raise AuthError("Not authenticated.")
    payload = decode_token(token, expected_type="access")
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except (ValueError, KeyError) as exc:
        raise AuthError("Invalid token subject.") from exc
    user = await db.get(AdminUser, user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise AuthError("User not found or inactive.")
    # Reject tokens minted before the latest password change / forced logout.
    if int(payload.get("tv", 0)) != user.token_version:
        raise AuthError("Session has been invalidated. Please sign in again.")
    # Phase 2: resolve the active account (tenant) + the user's role *within it*,
    # set the request-scoped tenant context, and stash the role for require_role.
    membership = await resolve_active_membership(db, user, _parse_uuid(payload.get("act")))
    if membership is not None:
        # A platform-admin disabled tenant blocks its members from acting under
        # it (platform admins themselves bypass this to manage it via /admin).
        from app.config import settings
        from app.models.account import Account

        account = await db.get(Account, membership.account_id)
        if (account is not None and account.disabled_at is not None
                and not settings.is_platform_admin(user.email)):
            raise AuthError("This workspace has been disabled. Contact support.")
        set_active_account(membership.account_id)
        request.state.account_id = membership.account_id
        request.state.account_role = membership.role
    else:  # legacy/pre-migration token with no membership: fall back to global role
        request.state.account_id = None
        request.state.account_role = user.role
    return user


CurrentUser = Annotated[AdminUser, Depends(get_current_user)]


def require_role(required: Role):
    """Dependency factory enforcing a minimum role *within the active account*."""

    async def _dep(request: Request, user: CurrentUser) -> AdminUser:
        role = getattr(request.state, "account_role", None) or user.role
        if not role_at_least(role, required):
            raise PermissionError_(
                f"This action requires '{required}' privileges.", code="insufficient_role"
            )
        return user

    return _dep


# Convenience dependencies.
require_authenticated = require_role(Role.viewer)
require_editor = require_role(Role.editor)
require_admin = require_role(Role.admin)
require_owner = require_role(Role.owner)


async def require_platform_admin(user: CurrentUser) -> AdminUser:
    """Platform super-admin gate — the /admin console. Membership is by the
    PLATFORM_ADMIN_EMAILS env allowlist, never a DB role, so there's no in-app
    escalation path. Normal login (password + 2FA) still applies."""
    from app.config import settings

    if not settings.is_platform_admin(user.email):
        raise PermissionError_("Platform admin access required.", code="not_platform_admin")
    return user


async def require_verified_email(user: CurrentUser) -> AdminUser:
    """Gate for actions with real external/reach effects (connecting a social
    account, inviting a teammate, publishing content) — not for the product
    generally, which unverified users can otherwise use normally."""
    if user.email_verified_at is None:
        raise PermissionError_(
            "Please verify your email address before doing this.",
            code="email_not_verified",
        )
    return user


async def verify_csrf(request: Request) -> None:
    """Double-submit CSRF check on state-changing requests."""
    if request.method in _SAFE_METHODS:
        return
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not csrf_tokens_match(cookie, header):
        raise PermissionError_("CSRF validation failed.", code="csrf_failed")
