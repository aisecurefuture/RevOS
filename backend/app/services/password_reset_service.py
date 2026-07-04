"""Password reset flow (stateless signed token, 1-hour expiry).

The token encodes the user's email + their current token_version. On reset,
token_version increments — invalidating the token and all existing sessions in
one step (no DB-side token table needed).

Rate limiting is enforced at the router layer, not here.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.core.exceptions import AuthError
from app.core.security import hash_password, make_signed_token, read_signed_token, validate_password_strength
from app.models.base import utcnow
from app.models.user import AdminUser
from app.services.transactional_email import send_transactional

logger = logging.getLogger("revos.password_reset")

_RESET_SALT = "password-reset"
_RESET_MAX_AGE = 3600  # 1 hour


def _make_reset_token(user: AdminUser) -> str:
    """Signed token binding email + current token_version (replay-safe)."""
    return make_signed_token(
        {"email": user.email, "tv": user.token_version},
        salt=_RESET_SALT,
    )


async def send_reset_email(db: AsyncSession, email: str) -> None:
    """Look up the user and send a reset link. Silent no-op if email not found
    (never reveal whether an address is registered)."""
    res = await db.execute(
        select(AdminUser).where(
            AdminUser.email == email.lower().strip(),
            AdminUser.deleted_at.is_(None),
        )
    )
    user = res.scalar_one_or_none()
    if user is None or not user.is_active:
        return  # don't leak existence

    token = _make_reset_token(user)
    reset_url = f"{settings.frontend_base_url}/reset-password?token={token}"

    try:
        send_transactional(
            to_email=user.email,
            subject="Reset your RevOS password",
            html=(
                f"<p>Hi {user.full_name or 'there'},</p>"
                f"<p>We received a request to reset your RevOS password. "
                f"Click the link below — it expires in 1 hour.</p>"
                f'<p><a href="{reset_url}">Reset password</a></p>'
                f"<p>If you did not request a reset, you can safely ignore this email. "
                f"Your password has not changed.</p>"
            ),
            text=(
                f"Reset your RevOS password: {reset_url}\n\n"
                f"This link expires in 1 hour. If you didn't request this, ignore it."
            ),
        )
    except Exception:
        logger.exception("Failed to send password reset email to %s", email)


async def apply_reset(db: AsyncSession, token: str, new_password: str) -> AdminUser:
    """Verify the reset token and set the new password.

    Raises AuthError on invalid/expired token or weak password.
    Increments token_version → invalidates this token + all active sessions.
    """
    try:
        data = read_signed_token(token, salt=_RESET_SALT, max_age_seconds=_RESET_MAX_AGE)
    except AuthError as exc:
        raise AuthError("Reset link is invalid or has expired.") from exc

    email = data.get("email", "")
    token_version = data.get("tv")

    res = await db.execute(
        select(AdminUser).where(
            AdminUser.email == email,
            AdminUser.deleted_at.is_(None),
        )
    )
    user = res.scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthError("Reset link is invalid or has expired.")

    # Reject replay: token_version must match what was in the token when it was minted.
    if user.token_version != token_version:
        raise AuthError("Reset link has already been used.")

    # Validate password strength (same rules as registration).
    validate_password_strength(new_password)

    user.password_hash = hash_password(new_password)
    user.token_version += 1  # invalidates this token + all existing sessions
    user.updated_at = utcnow()
    db.add(user)
    await db.flush()

    logger.info("Password reset completed for user %s", user.id)
    return user
