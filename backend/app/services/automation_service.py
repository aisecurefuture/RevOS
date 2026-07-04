"""Auto-approve automation (P3-M7).

An account can enable auto-approve to run hands-off: pending approvals are
executed automatically by a Celery-beat sweeper, with no human review, until an
optional expiry.

``execute_approval`` is shared with the interactive approve route so the two
paths dispatch identically — a human clicking Approve and the sweeper approving
on the owner's behalf run the exact same side effects.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import reset_active_account, set_active_account
from app.models.account import Account
from app.models.approval import ApprovalAction, ApprovalRequest, ApprovalStatus
from app.models.base import utcnow
from app.models.user import AdminUser
from app.services import approval_service

logger = logging.getLogger("revos.automation")

_SWEEP_LIMIT = 200


def is_auto_approve_active(account: Account) -> bool:
    """True if the account is currently in hands-off auto-approve mode."""
    if not account.auto_approve_enabled:
        return False
    if account.auto_approve_until is not None and account.auto_approve_until <= utcnow():
        return False
    return True


async def execute_approval(
    db: AsyncSession, approval: ApprovalRequest, actor: AdminUser
) -> int | None:
    """Approve + execute one pending request. The caller must have verified the
    request is still pending. Returns an emails-sent count where meaningful.

    Shared by the interactive approve route and the auto-approve sweeper so the
    dispatch never diverges.
    """
    if approval.action_type == ApprovalAction.social_publish:
        from app.services import social_connection_service
        # execute_publish marks the request approved and pushes to the platform.
        await social_connection_service.execute_publish(
            db, approval.id, approval.account_id, actor
        )
        return None

    await approval_service.mark_approved(db, approval, user_id=actor.id)
    if approval.action_type == ApprovalAction.campaign_send and approval.entity_id:
        from app.services import campaign_email_service
        return await campaign_email_service.execute_send(db, approval.entity_id)
    if approval.action_type == ApprovalAction.sequence_step_send and approval.entity_id:
        from app.services import sequence_engine
        return 1 if await sequence_engine.execute_step_run(db, approval.entity_id) else 0
    return None


async def run_auto_approvals(db: AsyncSession) -> dict:
    """Sweep every auto-approve account: execute its pending approvals, and
    disable any window that has lapsed. Each approval runs in its own savepoint
    so one failure never blocks the rest."""
    now = utcnow()
    accounts = (await db.execute(
        select(Account).where(Account.auto_approve_enabled.is_(True))
    )).scalars().all()

    approved = 0
    expired = 0
    for acct in accounts:
        if acct.auto_approve_until is not None and acct.auto_approve_until <= now:
            acct.auto_approve_enabled = False
            db.add(acct)
            expired += 1
            continue

        actor_id = acct.auto_approve_set_by or acct.owner_user_id
        actor = await db.get(AdminUser, actor_id)
        if actor is None:
            logger.warning("Auto-approve account %s has no valid actor; skipping", acct.id)
            continue

        reqs = (await db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.account_id == acct.id,
                ApprovalRequest.status == ApprovalStatus.pending,
            ).limit(_SWEEP_LIMIT)
        )).scalars().all()

        # Scope tenant reads/writes inside the executors to this account.
        token = set_active_account(acct.id)
        try:
            for req in reqs:
                try:
                    async with db.begin_nested():
                        await execute_approval(db, req, actor)
                    approved += 1
                except Exception:  # noqa: BLE001 — one bad approval must not stop the sweep
                    logger.exception("Auto-approve failed for approval %s", req.id)
        finally:
            reset_active_account(token)

    await db.flush()
    return {"approved": approved, "expired": expired}
