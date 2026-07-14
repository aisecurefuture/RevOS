"""Authentication service: user lookup, login, creation, password change."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.exceptions import AuthError, ConflictError
from app.core.security import (
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.models.base import utcnow
from app.models.user import AdminUser, Role

# A precomputed hash used to equalize timing when the email does not exist,
# mitigating user-enumeration via response-time differences.
_DUMMY_HASH = hash_password("revos-timing-equalizer-not-a-real-password-0")


async def get_user_by_email(db: AsyncSession, email: str) -> AdminUser | None:
    result = await db.execute(
        select(AdminUser).where(AdminUser.email == email.lower().strip())
    )
    return result.scalar_one_or_none()


async def authenticate_user(db: AsyncSession, email: str, password: str) -> AdminUser:
    """Verify credentials. Raises AuthError on any failure (generic message).

    Brute-force lockout: after ``login_max_failed_attempts`` bad passwords the
    account locks for ``login_lockout_minutes``; a platform admin can unlock
    early. Counters reset on a successful login.
    """
    from app.config import settings

    user = await get_user_by_email(db, email)
    if user is None:
        verify_password(password, _DUMMY_HASH)  # constant-time-ish dummy work
        raise AuthError("Invalid email or password.")

    if user.locked_until is not None and user.locked_until > utcnow():
        raise AuthError("Account temporarily locked due to failed logins. Try again later.")

    if not verify_password(password, user.hashed_password):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.login_max_failed_attempts:
            user.locked_until = utcnow() + timedelta(minutes=settings.login_lockout_minutes)
        db.add(user)
        # COMMIT before raising: the login request ends in an exception, which
        # rolls the session back — so the counter must be persisted here or
        # lockout would never accumulate.
        await db.commit()
        raise AuthError("Invalid email or password.")

    if not user.is_active or user.deleted_at is not None:
        raise AuthError("This account is disabled.")

    # Success — clear any accumulated failures / lock.
    if user.failed_login_count or user.locked_until:
        user.failed_login_count = 0
        user.locked_until = None
        db.add(user)
        await db.flush()
    return user


async def create_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str = "",
    role: Role = Role.viewer,
) -> AdminUser:
    email = email.lower().strip()
    if await get_user_by_email(db, email) is not None:
        raise ConflictError("A user with this email already exists.")
    validate_password_strength(password)
    user = AdminUser(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        role=role,
    )
    db.add(user)
    await db.flush()
    # Phase 2: every user gets a personal workspace + owner membership.
    from app.services.account_service import create_personal_account

    await create_personal_account(db, user)
    return user


async def change_password(
    db: AsyncSession, user: AdminUser, current_password: str, new_password: str
) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise AuthError("Current password is incorrect.")
    validate_password_strength(new_password)
    user.hashed_password = hash_password(new_password)
    # Invalidate every previously-issued token for this user.
    user.token_version += 1
    db.add(user)
    await db.flush()


async def update_last_login(db: AsyncSession, user: AdminUser) -> None:
    user.last_login_at = utcnow()
    db.add(user)
    await db.flush()
