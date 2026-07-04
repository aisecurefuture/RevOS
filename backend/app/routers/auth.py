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
from app.core.rate_limit import (
    RateLimitError,
    rate_limit_2fa,
    rate_limit_login,
    record_twofa_failure,
    twofa_account_allowed,
)
from app.core.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_csrf_token,
    make_signed_token,
    read_signed_token,
)
from app.deps import CurrentUser, DbSession, verify_csrf
from app.models.user import AdminUser, Role
from app.schemas.account import AcceptInvitationRequest, RegisterRequest
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    RecoveryCodesResponse,
    ResetPasswordRequest,
    TwoFACodeRequest,
    TwoFADisableRequest,
    TwoFALoginRequest,
    TwoFASetupResponse,
    UpdateProfileRequest,
    UserOut,
)
from app.services import invitation_service, password_reset_service, twofa_service, verification_service
from app.services.account_service import resolve_active_membership
from app.services.auth_service import (
    authenticate_user,
    change_password,
    create_user,
    update_last_login,
)

_2FA_SALT = "2fa-pending"
_2FA_MAX_AGE = 300  # a 2FA challenge is valid for 5 minutes

router = APIRouter(prefix="/auth", tags=["auth"])

_CSRF_MAX_AGE = 60 * 60 * 8


def _set_auth_cookies(
    response: Response,
    user: AdminUser,
    csrf_token: str,
    *,
    active_account: str | None = None,
    role: str | None = None,
) -> None:
    access = create_access_token(
        str(user.id), role or user.role, user.token_version, active_account=active_account
    )
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


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: DbSession,
    _rl: None = Depends(rate_limit_login),
):
    user = await authenticate_user(db, body.email, body.password)
    # 2FA gate: password is correct, but issue only a short-lived challenge token
    # (no session) until the second factor is provided.
    if user.totp_enabled:
        pending = make_signed_token(
            {"uid": str(user.id), "tv": user.token_version}, salt=_2FA_SALT
        )
        await write_audit(db, action="auth.login.2fa_challenge", user_id=user.id, request=request)
        return {"twofa_required": True, "pending_token": pending}
    await update_last_login(db, user)
    membership = await resolve_active_membership(db, user, None)
    active_account = str(membership.account_id) if membership else None
    role = membership.role if membership else user.role
    csrf = generate_csrf_token()
    _set_auth_cookies(response, user, csrf, active_account=active_account, role=role)
    await write_audit(db, action="auth.login", user_id=user.id, request=request)
    return LoginResponse(user=UserOut.model_validate(user), csrf_token=csrf)


@router.post("/register", response_model=LoginResponse, status_code=201)
async def register(
    request: Request,
    response: Response,
    body: RegisterRequest,
    db: DbSession,
    _rl: None = Depends(rate_limit_login),
) -> LoginResponse:
    """Self-signup: creates the user + their personal workspace, then logs them
    in. New signups own their personal account."""
    user = await create_user(
        db, email=body.email, password=body.password,
        full_name=body.full_name, role=Role.owner,
    )
    membership = await resolve_active_membership(db, user, None)
    active_account = str(membership.account_id) if membership else None
    role = membership.role if membership else user.role
    csrf = generate_csrf_token()
    _set_auth_cookies(response, user, csrf, active_account=active_account, role=role)
    await write_audit(db, action="auth.register", user_id=user.id, request=request)
    # Send email verification in background (best-effort; non-fatal if it fails).
    try:
        verification_service.send_verification_email(user)
    except Exception:
        pass
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
    membership = await resolve_active_membership(db, user, None)
    active_account = str(membership.account_id) if membership else None
    role = membership.role if membership else user.role
    csrf = generate_csrf_token()
    _set_auth_cookies(response, user, csrf, active_account=active_account, role=role)
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


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: UpdateProfileRequest,
    user: CurrentUser,
    db: DbSession,
    _: None = Depends(verify_csrf),
) -> UserOut:
    """Update the current user's profile (name, timezone, avatar, notifications)."""
    if body.full_name is not None:
        user.full_name = body.full_name.strip()
    settings_patch: dict = {}
    if body.timezone is not None:
        settings_patch["timezone"] = body.timezone
    if body.avatar_url is not None:
        settings_patch["avatar_url"] = body.avatar_url
    if body.notifications is not None:
        settings_patch["notifications"] = body.notifications
    if settings_patch:
        user.settings = {**(user.settings or {}), **settings_patch}
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return UserOut.model_validate(user)


@router.get("/verify-email")
async def verify_email(token: str, db: DbSession) -> dict:
    """Consume an email verification link (GET so it works as a plain href)."""
    user = await verification_service.verify_email_token(db, token)
    return {"status": "verified", "email": user.email}


@router.post("/verify-email/resend")
async def resend_verification(
    user: CurrentUser,
    _: None = Depends(verify_csrf),
) -> dict:
    """Re-send the verification email (rate-limiting left to the login RL dep)."""
    if user.email_verified_at is not None:
        return {"status": "already_verified"}
    try:
        verification_service.send_verification_email(user)
    except Exception:
        pass
    return {"status": "sent"}


@router.post("/invitation/accept")
async def accept_invitation(
    body: AcceptInvitationRequest,
    user: CurrentUser,
    db: DbSession,
    _: None = Depends(verify_csrf),
) -> dict:
    """Exchange an invitation token for a membership in the invited account."""
    membership = await invitation_service.accept_invitation(db, body.token, user)
    return {"account_id": str(membership.account_id), "role": membership.role}


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


# --- 2FA (TOTP) -------------------------------------------------------------
@router.post("/2fa/setup", response_model=TwoFASetupResponse)
async def twofa_setup(
    user: CurrentUser, db: DbSession, _: None = Depends(verify_csrf)
) -> TwoFASetupResponse:
    secret, uri = await twofa_service.start_setup(db, user)
    return TwoFASetupResponse(secret=secret, otpauth_uri=uri)


@router.post("/2fa/verify", response_model=RecoveryCodesResponse)
async def twofa_verify(
    request: Request, body: TwoFACodeRequest, user: CurrentUser, db: DbSession,
    _: None = Depends(verify_csrf),
    _rl: None = Depends(rate_limit_2fa),
) -> RecoveryCodesResponse:
    codes = await twofa_service.confirm_setup(db, user, body.code)
    await write_audit(db, action="auth.2fa.enabled", user_id=user.id, request=request)
    return RecoveryCodesResponse(recovery_codes=codes)


@router.post("/2fa/disable")
async def twofa_disable(
    request: Request, body: TwoFADisableRequest, user: CurrentUser, db: DbSession,
    _: None = Depends(verify_csrf),
    _rl: None = Depends(rate_limit_2fa),
) -> dict:
    await twofa_service.disable(db, user, body.password, body.code)
    await write_audit(db, action="auth.2fa.disabled", user_id=user.id, request=request)
    return {"status": "disabled"}


# --- Password reset ---------------------------------------------------------
@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    db: DbSession,
    _rl: None = Depends(rate_limit_login),
) -> dict:
    """Send a password-reset link. Always returns 200 (don't reveal if email exists)."""
    await password_reset_service.send_reset_email(db, body.email)
    return {"status": "ok"}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, db: DbSession) -> dict:
    """Apply a password reset using the signed token from the email link."""
    await password_reset_service.apply_reset(db, body.token, body.password)
    return {"status": "password_reset"}


@router.post("/2fa/login", response_model=LoginResponse)
async def twofa_login(
    request: Request, response: Response, body: TwoFALoginRequest, db: DbSession,
    _rl: None = Depends(rate_limit_login),
) -> LoginResponse:
    """Second step of a 2FA login: exchange the challenge token + a TOTP/recovery
    code for a full session."""
    try:
        data = read_signed_token(body.pending_token, salt=_2FA_SALT, max_age_seconds=_2FA_MAX_AGE)
    except AuthError as exc:
        raise AuthError("Your 2FA session expired. Please sign in again.") from exc
    user = await db.get(AdminUser, uuid.UUID(str(data["uid"])))
    if (
        user is None or not user.is_active or user.deleted_at is not None
        or int(data.get("tv", 0)) != user.token_version
    ):
        raise AuthError("Your 2FA session is no longer valid. Please sign in again.")
    # Per-account brute-force guard: caps failed code attempts even when the
    # attacker rotates source IPs. Checked before verifying so an exhausted
    # budget short-circuits to 429.
    if not twofa_account_allowed(str(user.id)):
        await write_audit(db, action="auth.login.2fa_rate_limited", user_id=user.id, request=request)
        raise RateLimitError("Too many 2FA attempts. Please wait a few minutes and try again.")
    if not await twofa_service.verify_second_factor(db, user, body.code):
        record_twofa_failure(str(user.id))
        await write_audit(db, action="auth.login.2fa_failed", user_id=user.id, request=request)
        raise AuthError("Invalid authentication code.")
    await update_last_login(db, user)
    membership = await resolve_active_membership(db, user, None)
    active_account = str(membership.account_id) if membership else None
    role = membership.role if membership else user.role
    csrf = generate_csrf_token()
    _set_auth_cookies(response, user, csrf, active_account=active_account, role=role)
    await write_audit(db, action="auth.login.2fa_success", user_id=user.id, request=request)
    return LoginResponse(user=UserOut.model_validate(user), csrf_token=csrf)
