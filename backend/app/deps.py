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
from app.database import get_session
from app.models.user import AdminUser, Role

DbSession = Annotated[AsyncSession, Depends(get_session)]

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
    return user


CurrentUser = Annotated[AdminUser, Depends(get_current_user)]


def require_role(required: Role):
    """Dependency factory enforcing a minimum role."""

    async def _dep(user: CurrentUser) -> AdminUser:
        if not role_at_least(user.role, required):
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


async def verify_csrf(request: Request) -> None:
    """Double-submit CSRF check on state-changing requests."""
    if request.method in _SAFE_METHODS:
        return
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not csrf_tokens_match(cookie, header):
        raise PermissionError_("CSRF validation failed.", code="csrf_failed")
