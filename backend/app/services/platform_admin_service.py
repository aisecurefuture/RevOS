"""Platform super-admin operations (the /admin console).

Cross-tenant, above the per-account RBAC. Every caller is gated by
``require_platform_admin`` (the PLATFORM_ADMIN_EMAILS allowlist) at the router,
so these functions assume the actor is a trusted platform operator.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.account import Account, Membership
from app.models.base import utcnow
from app.models.billing import PlanName, Subscription, SubscriptionStatus
from app.models.user import AdminUser, Role


async def list_accounts(db: AsyncSession) -> list[dict]:
    """All tenants with owner + member count + status."""
    result = await db.execute(select(Account).where(Account.deleted_at.is_(None)).order_by(Account.created_at.desc()))
    accounts = list(result.scalars().all())
    out = []
    for acct in accounts:
        owner = await db.get(AdminUser, acct.owner_user_id)
        count = await db.scalar(
            select(func.count()).select_from(Membership).where(
                Membership.account_id == acct.id, Membership.deleted_at.is_(None)
            )
        )
        sub = (await db.execute(
            select(Subscription).where(Subscription.account_id == acct.id)
        )).scalar_one_or_none()
        out.append({
            "id": acct.id, "name": acct.name, "slug": acct.slug, "type": str(acct.type),
            "owner_email": owner.email if owner else None,
            "member_count": int(count or 0),
            "disabled": acct.disabled_at is not None,
            "disabled_reason": acct.disabled_reason,
            "plan": str(sub.plan) if sub else None,
            "billing_status": str(sub.status) if sub else None,
            "created_at": acct.created_at,
        })
    return out


async def list_users(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(AdminUser).where(AdminUser.deleted_at.is_(None)).order_by(AdminUser.created_at.desc())
    )
    users = list(result.scalars().all())
    now = utcnow()
    return [{
        "id": u.id, "email": u.email, "full_name": u.full_name,
        "is_active": u.is_active,
        "locked": u.locked_until is not None and u.locked_until > now,
        "failed_login_count": u.failed_login_count,
        "email_verified": u.email_verified_at is not None,
        "created_at": u.created_at,
    } for u in users]


async def set_account_disabled(
    db: AsyncSession, account_id: uuid.UUID, actor: AdminUser, *, disabled: bool, reason: str | None = None
) -> Account:
    acct = await db.get(Account, account_id)
    if acct is None or acct.deleted_at is not None:
        raise NotFoundError("Account not found.")
    if disabled:
        acct.disabled_at = utcnow()
        acct.disabled_by = actor.id
        acct.disabled_reason = (reason or "")[:300] or None
    else:
        acct.disabled_at = None
        acct.disabled_by = None
        acct.disabled_reason = None
    db.add(acct)
    await db.flush()
    return acct


async def set_account_comp(
    db: AsyncSession, account_id: uuid.UUID, *, enabled: bool,
) -> Subscription:
    """Grant or revoke complimentary (no-billing) access for an account.

    Granting upserts the account's subscription to plan=comp / status=active
    with no period end — the paywall never triggers. Revoking only applies to
    an account that is actually on comp (it will NOT touch a real paid Stripe
    subscription) and drops it to canceled, which restores the normal paywall.
    """
    acct = await db.get(Account, account_id)
    if acct is None or acct.deleted_at is not None:
        raise NotFoundError("Account not found.")

    sub = (await db.execute(
        select(Subscription).where(Subscription.account_id == account_id)
    )).scalar_one_or_none()

    if enabled:
        if sub is None:
            sub = Subscription(account_id=account_id)
        if sub.status == SubscriptionStatus.active and sub.plan not in (PlanName.trial, PlanName.comp):
            raise ConflictError(
                "This account has an active paid subscription — comp access "
                "would be a downgrade of their paid plan. Cancel it in Stripe first."
            )
        sub.plan = PlanName.comp
        sub.status = SubscriptionStatus.active
        sub.trial_ends_at = None
        sub.current_period_end = None
        sub.billing_interval = None
        sub.canceled_at = None
        sub.cancel_at_period_end = False
    else:
        if sub is None or sub.plan != PlanName.comp:
            raise ConflictError("This account is not on complimentary access.")
        sub.status = SubscriptionStatus.canceled
        sub.canceled_at = utcnow()

    db.add(sub)
    await db.flush()
    return sub


async def set_user_active(db: AsyncSession, user_id: uuid.UUID, *, active: bool) -> AdminUser:
    user = await db.get(AdminUser, user_id)
    if user is None or user.deleted_at is not None:
        raise NotFoundError("User not found.")
    user.is_active = active
    if not active:
        user.token_version += 1  # kill their sessions immediately
    db.add(user)
    await db.flush()
    return user


async def unlock_user(db: AsyncSession, user_id: uuid.UUID) -> AdminUser:
    """Clear a brute-force lockout (and reset the failure counter)."""
    user = await db.get(AdminUser, user_id)
    if user is None or user.deleted_at is not None:
        raise NotFoundError("User not found.")
    user.locked_until = None
    user.failed_login_count = 0
    db.add(user)
    await db.flush()
    return user


async def create_tenant(
    db: AsyncSession, actor: AdminUser, *, name: str, lead_email: str, lead_name: str = "",
) -> dict:
    """Create a team account and designate a lead.

    If the lead already has a user, they become the owner immediately. If not,
    the account is created owned by the actor and the lead is invited (they
    become owner on acceptance is out of scope; they join as admin). Either
    way the lead is emailed.
    """
    from app.services import account_service, invitation_service

    lead_email = lead_email.lower().strip()
    lead = (await db.execute(select(AdminUser).where(AdminUser.email == lead_email))).scalar_one_or_none()

    if lead is not None:
        account = await account_service.create_team_account(db, lead, name)
        invited = False
    else:
        # No user yet: actor owns the shell; lead is invited as admin.
        account = await account_service.create_team_account(db, actor, name)
        await invitation_service.send_invitation(db, account.id, actor, lead_email, "admin")
        invited = True

    return {
        "account_id": account.id, "name": account.name, "slug": account.slug,
        "lead_email": lead_email, "invited": invited,
    }
