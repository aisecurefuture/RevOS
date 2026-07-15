"""Email login one-time code — the anti-bot second step at login.

Only active when email delivery is actually enabled (a misconfigured mailer
must never be able to lock everyone out) and only for users WITHOUT app-based
2FA (they already have a second factor). A valid trusted-device cookie also
skips it — see the auth router.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import hash_password, verify_password
from app.models.base import utcnow
from app.models.user import AdminUser, EmailLoginCode
from app.services.transactional_email import send_transactional


def feature_active() -> bool:
    """The email-code step is on AND email can actually be delivered."""
    return settings.login_email_otp and settings.email_enabled


def should_challenge(user: AdminUser, trusted_device: bool) -> bool:
    return (
        feature_active()
        and not user.totp_enabled  # app 2FA already covers them
        and not trusted_device
    )


async def create_and_send(db: AsyncSession, user: AdminUser) -> None:
    """Generate a fresh 6-digit code, replace any prior code, email it."""
    # Invalidate old codes for this user.
    old = await db.execute(
        select(EmailLoginCode).where(
            EmailLoginCode.user_id == user.id, EmailLoginCode.used_at.is_(None),
            EmailLoginCode.deleted_at.is_(None),
        )
    )
    for c in old.scalars().all():
        c.deleted_at = utcnow()
        db.add(c)

    code = f"{secrets.randbelow(1_000_000):06d}"
    row = EmailLoginCode(
        user_id=user.id,
        code_hash=hash_password(code),
        expires_at=utcnow() + timedelta(minutes=settings.login_otp_ttl_minutes),
    )
    db.add(row)
    await db.commit()  # persist before the (possibly slow) email send

    send_transactional(
        to_email=user.email,
        subject=f"Your RevOS login code: {code}",
        html=(
            f"<p>Hi {user.full_name or 'there'},</p>"
            f"<p>Your one-time login code is:</p>"
            f'<p style="font-size:24px;font-weight:bold;letter-spacing:3px">{code}</p>'
            f"<p>It expires in {settings.login_otp_ttl_minutes} minutes. If you didn't try to "
            f"sign in, someone may have your password — change it right away.</p>"
        ),
        text=f"Your RevOS login code is {code} (expires in {settings.login_otp_ttl_minutes} minutes).",
    )


async def verify(db: AsyncSession, user_id: uuid.UUID, code: str) -> bool:
    """Check a submitted code. Consumes it on success; counts attempts and
    stops accepting once the per-code attempt budget is spent."""
    res = await db.execute(
        select(EmailLoginCode).where(
            EmailLoginCode.user_id == user_id, EmailLoginCode.used_at.is_(None),
            EmailLoginCode.deleted_at.is_(None),
        ).order_by(EmailLoginCode.created_at.desc())
    )
    row = res.scalars().first()
    if row is None or row.expires_at < utcnow():
        return False
    if row.attempts >= settings.login_otp_max_attempts:
        return False
    row.attempts += 1
    ok = verify_password(code.strip(), row.code_hash)
    if ok:
        row.used_at = utcnow()
    db.add(row)
    await db.commit()  # persist attempt count / consumption regardless of outcome
    return ok
