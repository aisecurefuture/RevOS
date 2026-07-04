"""TOTP 2FA enrollment + verification (Phase 2 M2)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.exceptions import AuthError, ConflictError
from app.core.security import verify_password
from app.core.totp import (
    decrypt_secret,
    encrypt_secret,
    generate_recovery_codes,
    hash_recovery_code,
    new_secret,
    provisioning_uri,
    verify_code,
)
from app.models.base import utcnow
from app.models.user import AdminUser, RecoveryCode


async def _clear_recovery_codes(db: AsyncSession, user_id) -> None:
    res = await db.execute(select(RecoveryCode).where(RecoveryCode.user_id == user_id))
    for rc in res.scalars().all():
        await db.delete(rc)
    await db.flush()


async def start_setup(db: AsyncSession, user: AdminUser) -> tuple[str, str]:
    """Generate + store (encrypted) a new secret, not yet enabled. Returns
    (secret, otpauth_uri) for the client to render as a QR code."""
    if user.totp_enabled:
        raise ConflictError("2FA is already enabled. Disable it first to re-enroll.")
    secret = new_secret()
    user.totp_secret_enc = encrypt_secret(secret)
    db.add(user)
    await db.flush()
    return secret, provisioning_uri(secret, user.email)


async def confirm_setup(db: AsyncSession, user: AdminUser, code: str) -> list[str]:
    """Verify a code against the pending secret, enable 2FA, and return fresh
    one-time recovery codes (shown once)."""
    if not user.totp_secret_enc:
        raise AuthError("Start 2FA setup before verifying.")
    secret = decrypt_secret(user.totp_secret_enc)
    if secret is None or not verify_code(secret, code):
        raise AuthError("That code is incorrect. Try again.")
    user.totp_enabled = True
    user.totp_confirmed_at = utcnow()
    await _clear_recovery_codes(db, user.id)
    codes = generate_recovery_codes()
    for c in codes:
        db.add(RecoveryCode(user_id=user.id, code_hash=hash_recovery_code(c)))
    db.add(user)
    await db.flush()
    return codes


async def verify_second_factor(db: AsyncSession, user: AdminUser, code: str) -> bool:
    """Accept either a current TOTP code or an unused recovery code (burned on use)."""
    if user.totp_secret_enc:
        secret = decrypt_secret(user.totp_secret_enc)
        if secret and verify_code(secret, code):
            return True
    res = await db.execute(
        select(RecoveryCode).where(
            RecoveryCode.user_id == user.id,
            RecoveryCode.code_hash == hash_recovery_code(code),
            RecoveryCode.used_at.is_(None),
        )
    )
    rc = res.scalar_one_or_none()
    if rc is not None:
        rc.used_at = utcnow()
        db.add(rc)
        await db.flush()
        return True
    return False


async def disable(db: AsyncSession, user: AdminUser, password: str, code: str) -> None:
    """Turn 2FA off — requires re-auth (password + a current code/recovery code)."""
    if not verify_password(password, user.hashed_password):
        raise AuthError("Current password is incorrect.")
    if not await verify_second_factor(db, user, code):
        raise AuthError("That code is incorrect.")
    user.totp_enabled = False
    user.totp_secret_enc = None
    user.totp_confirmed_at = None
    await _clear_recovery_codes(db, user.id)
    db.add(user)
    await db.flush()
