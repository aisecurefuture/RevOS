"""Account (workspace) + membership operations (Phase 2 M1).

Keeps tenancy logic in one place: creating a user's personal account, resolving
which account a request acts in, and looking up per-account roles.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.account import Account, AccountType, Membership
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
    return account


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
