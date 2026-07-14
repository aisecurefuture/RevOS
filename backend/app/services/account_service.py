"""Account (workspace) + membership operations (Phase 2 M1).

Keeps tenancy logic in one place: creating a user's personal account, resolving
which account a request acts in, and looking up per-account roles.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.core.exceptions import ConflictError, NotFoundError, PermissionError_
from app.core.rbac import role_at_least

from app.models.account import Account, AccountType, Membership
from app.models.base import utcnow
from app.models.user import AdminUser, Role


def _slugify(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (base or "account")[:100]


async def create_personal_account(db: AsyncSession, user: AdminUser) -> Account:
    """Create a user's personal workspace + owner membership. Idempotent-ish:
    callers create this once, at user creation."""
    account = Account(
        type=AccountType.personal,
        name=(user.full_name or user.email.split("@")[0]),
        slug=f"{_slugify(user.full_name or user.email.split('@')[0])}-{uuid.uuid4().hex[:6]}",
        owner_user_id=user.id,
    )
    db.add(account)
    await db.flush()  # assign account.id
    # The user's role carries into their personal workspace. Self-signup creates
    # owners; an admin-provisioned lower-role user stays that role in their space.
    db.add(Membership(user_id=user.id, account_id=account.id, role=user.role or Role.owner))
    await db.flush()
    # Every new account starts with a trial subscription.
    from app.services.billing_service import provision_trial
    await provision_trial(db, account.id)
    return account


async def create_team_account(db: AsyncSession, user: AdminUser, name: str) -> Account:
    """Create a team workspace owned by the user (owner membership)."""
    account = Account(
        type=AccountType.team,
        name=name.strip(),
        slug=f"{_slugify(name)}-{uuid.uuid4().hex[:6]}",
        owner_user_id=user.id,
    )
    db.add(account)
    await db.flush()
    db.add(Membership(user_id=user.id, account_id=account.id, role=Role.owner))
    await db.flush()
    # Every new account starts with a trial subscription.
    from app.services.billing_service import provision_trial
    await provision_trial(db, account.id)
    return account


async def accounts_for_user(
    db: AsyncSession, user_id: uuid.UUID
) -> list[tuple[Account, Role]]:
    """The (account, role) pairs the user belongs to, oldest first."""
    res = await db.execute(
        select(Account, Membership.role)
        .join(Membership, Membership.account_id == Account.id)
        .where(
            Membership.user_id == user_id,
            Membership.deleted_at.is_(None),
            Account.deleted_at.is_(None),
        )
        .order_by(Membership.created_at.asc())
    )
    return [(a, r) for a, r in res.all()]


async def list_members(db: AsyncSession, account_id: uuid.UUID) -> list[tuple[AdminUser, Role]]:
    res = await db.execute(
        select(AdminUser, Membership.role)
        .join(Membership, Membership.user_id == AdminUser.id)
        .where(Membership.account_id == account_id, Membership.deleted_at.is_(None))
        .order_by(Membership.created_at.asc())
    )
    return [(u, r) for u, r in res.all()]


async def get_membership(
    db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID
) -> Membership | None:
    res = await db.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.account_id == account_id,
            Membership.deleted_at.is_(None),
        )
    )
    return res.scalar_one_or_none()


async def list_memberships(db: AsyncSession, user_id: uuid.UUID) -> list[Membership]:
    res = await db.execute(
        select(Membership)
        .where(Membership.user_id == user_id, Membership.deleted_at.is_(None))
        .order_by(Membership.created_at.asc())
    )
    return list(res.scalars().all())


async def remove_member(
    db: AsyncSession,
    account_id: uuid.UUID,
    target_user_id: uuid.UUID,
    requester: Membership,
) -> None:
    """Remove a member from an account. Requires owner role. Cannot remove the owner."""
    if not role_at_least(requester.role, Role.owner):
        raise PermissionError_("Only account owners can remove members.")
    if target_user_id == requester.user_id:
        raise ConflictError("You cannot remove yourself. Transfer ownership first.")
    res = await db.execute(
        select(Membership).where(
            Membership.user_id == target_user_id,
            Membership.account_id == account_id,
            Membership.deleted_at.is_(None),
        )
    )
    target = res.scalar_one_or_none()
    if target is None:
        raise NotFoundError("Member not found in this account.")
    if target.role == Role.owner:
        raise PermissionError_("Cannot remove the account owner.")
    target.deleted_at = utcnow()
    db.add(target)
    await db.flush()


async def change_member_role(
    db: AsyncSession,
    account_id: uuid.UUID,
    target_user_id: uuid.UUID,
    new_role: Role,
    requester: Membership,
) -> Membership:
    """Change a member's role. Requires owner role. Cannot demote the owner."""
    if not role_at_least(requester.role, Role.owner):
        raise PermissionError_("Only account owners can change member roles.")
    res = await db.execute(
        select(Membership).where(
            Membership.user_id == target_user_id,
            Membership.account_id == account_id,
            Membership.deleted_at.is_(None),
        )
    )
    target = res.scalar_one_or_none()
    if target is None:
        raise NotFoundError("Member not found in this account.")
    if target.role == Role.owner:
        raise PermissionError_("Cannot change the account owner's role.")
    target.role = new_role
    db.add(target)
    await db.flush()
    return target


async def admin_reset_member_password(
    db: AsyncSession,
    account_id: uuid.UUID,
    target_user_id: uuid.UUID,
    requester: Membership,
    *,
    mode: str,
) -> dict:
    """Admin/owner resets another member's password.

    Two modes so it works whether or not email is configured:
      * ``link`` — email the member a self-service reset link.
      * ``temp`` — generate a strong temporary password, set it, invalidate
        the member's existing sessions, and RETURN it once so the admin can
        relay it (works even when email delivery is down).

    Guards: requester must be admin+ of the account; only an owner may reset a
    member who is themselves an admin or owner (so an admin can't hijack an
    owner). A member can't reset their own password here (use change-password).
    """
    import secrets

    from app.core.security import hash_password
    from app.services import password_reset_service

    if not role_at_least(requester.role, Role.admin):
        raise PermissionError_("Admin access required to reset a member's password.")
    if target_user_id == requester.user_id:
        raise PermissionError_("Use the change-password flow for your own account.")

    target = await get_membership(db, target_user_id, account_id)
    if target is None:
        raise NotFoundError("Member not found in this account.")
    if role_at_least(target.role, Role.admin) and not role_at_least(requester.role, Role.owner):
        raise PermissionError_("Only the account owner can reset an admin or owner's password.")

    user = await db.get(AdminUser, target_user_id)
    if user is None or user.deleted_at is not None:
        raise NotFoundError("Member not found.")

    if mode == "link":
        await password_reset_service.send_reset_email(db, user.email)
        return {"mode": "link", "email": user.email, "emailed": settings.email_enabled}

    if mode == "temp":
        # url-safe, ~16 chars, mixed — meets validate_password_strength.
        temp = secrets.token_urlsafe(12) + "Aa1!"
        user.hashed_password = hash_password(temp)
        user.token_version += 1  # kill all existing sessions for this user
        db.add(user)
        await db.flush()
        return {"mode": "temp", "email": user.email, "temporary_password": temp}

    raise PermissionError_(f"Unknown reset mode: {mode}")


async def resolve_active_membership(
    db: AsyncSession, user: AdminUser, requested_account_id: uuid.UUID | None
) -> Membership | None:
    """Pick the membership the request should act under.

    A valid requested account (the JWT `act`) wins; otherwise fall back to the
    user's first membership (their personal account). Returns None only if the
    user somehow has no memberships.
    """
    if requested_account_id is not None:
        m = await get_membership(db, user.id, requested_account_id)
        if m is not None:
            return m
    memberships = await list_memberships(db, user.id)
    return memberships[0] if memberships else None
