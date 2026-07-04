"""Email verification flow (Phase 2 M2).

On sign-up a signed, 72-hour link is emailed.  Clicking it marks
`admin_users.email_verified_at`.  The token is stateless (no DB row) so there
is nothing to clean up on expiry — the link just stops working.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import AuthError
from app.core.security import make_signed_token, read_signed_token
from app.models.base import utcnow
from app.models.user import AdminUser
from app.services.transactional_email import send_transactional

_VERIFY_SALT = "email-verify"
_VERIFY_MAX_AGE = 72 * 3600  # 72 hours


def make_verification_token(user: AdminUser) -> str:
    return make_signed_token({"uid": str(user.id), "ev": 1}, salt=_VERIFY_SALT)


def send_verification_email(user: AdminUser) -> str:
    """Send the verification email and return the token (for tests + link-copy UI)."""
    token = make_verification_token(user)
    verify_url = f"{settings.frontend_base_url}/verify-email?token={token}"
    send_transactional(
        to_email=user.email,
        subject="Verify your RevOS email address",
        html=(
            f"<p>Hi {user.full_name or 'there'},</p>"
            f"<p>Please verify your email address to activate your RevOS account.</p>"
            f'<p><a href="{verify_url}">Verify email</a></p>'
            f"<p>This link expires in 72 hours. If you did not sign up, ignore this email.</p>"
        ),
        text=f"Verify your RevOS email: {verify_url}\n\nExpires in 72 hours.",
    )
    return token


async def verify_email_token(db: AsyncSession, token: str) -> AdminUser:
    """Consume a verification token. Raises AuthError if invalid/expired.
    Idempotent: already-verified users are returned without error."""
    try:
        data = read_signed_token(token, salt=_VERIFY_SALT, max_age_seconds=_VERIFY_MAX_AGE)
    except AuthError as exc:
        raise AuthError("Verification link is invalid or has expired.") from exc

    user = await db.get(AdminUser, uuid.UUID(str(data["uid"])))
    if user is None or not user.is_active or user.deleted_at is not None:
        raise AuthError("User not found.")

    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
        db.add(user)
        await db.flush()

    return user
