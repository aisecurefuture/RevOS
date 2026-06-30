"""Authentication router: login, logout, refresh, me, password change.

Tokens are delivered as cookies:
- ``revos_access``  — HttpOnly access JWT (short-lived).
- ``revos_refresh`` — HttpOnly refresh JWT, path-scoped to /api/auth.
- ``revos_csrf``    — readable double-submit CSRF token.
Login is rate-limited per IP to blunt credential stuffing.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response

from app.config import settings
from app.core.audit import write_audit
from app.core.exceptions import AuthError
from app.core.rate_limit import rate_limit_login
from app.core.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_csrf_token,
)
from app.deps import CurrentUser, DbSession, verify_csrf
from app.models.user import AdminUser
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    UserOut,
)
from app.services.auth_service import (
    authenticate_user,
    change_password,
    update_last_login,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_CSRF_MAX_AGE = 60 * 60 * 8


def _set_auth_cookies(response: Response, user: AdminUser, csrf_token: str) -> None:
    access = create_access_token(str(user.id), user.role, user.token_version)
    refresh = create_refresh_token(str(user.id), user.token_version)
    secure = settings.cookie_secure
    samesite = settings.cookie_samesite

    response.set_cookie(
        ACCESS_COOKIE, access,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True, secure=secure, samesite=samesite, path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE, refresh,
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=True, secure=secure, samesite=samesite, path="/api/auth",
    )
    # CSRF cookie is intentionally readable by JS (double-submit pattern).
    response.set_cookie(
        CSRF_COOKIE, csrf_token,
        max_age=_CSRF_MAX_AGE,
        httponly=False, secure=secure, samesite=samesite, path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: DbSession,
    _rl: None = Depends(rate_limit_login),
) -> LoginResponse:
    user = await authenticate_user(db, body.email, body.password)
    await update_last_login(db, user)
    csrf = generate_csrf_token()
    _set_auth_cookies(response, user, csrf)
    await write_audit(db, action="auth.login", user_id=user.id, request=request)
    return LoginResponse(user=UserOut.model_validate(user), csrf_token=csrf)


@router.post("/refresh", response_model=LoginResponse)
async def refresh(request: Request, response: Response, db: DbSession) -> LoginResponse:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise AuthError("No refresh token present.")
    payload = decode_token(token, expected_type="refresh")
    user = await db.get(AdminUser, uuid.UUID(str(payload["sub"])))
    if user is None or not user.is_active or user.deleted_at is not None:
        raise AuthError("User not found or inactive.")
    # Refresh tokens minted before a password change are rejected.
    if int(payload.get("tv", 0)) != user.token_version:
        raise AuthError("Session has been invalidated. Please sign in again.")
    csrf = generate_csrf_token()
    _set_auth_cookies(response, user, csrf)
    return LoginResponse(user=UserOut.model_validate(user), csrf_token=csrf)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    user: CurrentUser,
    db: DbSession,
    _: None = Depends(verify_csrf),
) -> dict:
    _clear_auth_cookies(response)
    await write_audit(db, action="auth.logout", user_id=user.id, request=request)
    return {"status": "logged_out"}


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/password")
async def change_pw(
    request: Request,
    body: PasswordChangeRequest,
    user: CurrentUser,
    db: DbSession,
    _: None = Depends(verify_csrf),
) -> dict:
    await change_password(db, user, body.current_password, body.new_password)
    await write_audit(db, action="auth.password_change", user_id=user.id, request=request)
    return {"status": "password_changed"}
