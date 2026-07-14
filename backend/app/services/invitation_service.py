"""Account invitation flow (Phase 2 M2).

Admins invite people by email.  The invitee receives a signed 7-day link.
On acceptance their account is added to the account with the specified role.
Email-matching prevents link forwarding to a different person.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.core.exceptions import AuthError, ConflictError, NotFoundError, PermissionError_
from app.core.security import make_signed_token, read_signed_token
from app.models.account import Invitation, Membership
from app.models.base import utcnow
from app.models.user import AdminUser, Role
from app.services.transactional_email import send_transactional

_INVITE_SALT = "account-invite"
_INVITE_MAX_AGE = 7 * 24 * 3600  # 7 days


def _make_invite_token(invite_id: uuid.UUID) -> str:
    return make_signed_token({"iid": str(invite_id)}, salt=_INVITE_SALT)


async def send_invitation(
    db: AsyncSession,
    account_id: uuid.UUID,
    invited_by: AdminUser,
    email: str,
    role: str,
) -> tuple[Invitation, str]:
    """Create (or refresh) an invitation and send the link email.

    Returns (invitation, token) so the API can expose the accept URL for
    link-copy and testing.  If a non-accepted invite already exists for this
    email+account it is refreshed (new role, new token) rather than duplicated.
    """
    email = email.lower().strip()

    # Reject if already a member
    res = await db.execute(
        select(Membership)
        .join(AdminUser, Membership.user_id == AdminUser.id)
        .where(
            Membership.account_id == account_id,
            AdminUser.email == email,
            Membership.deleted_at.is_(None),
        )
    )
    if res.scalar_one_or_none() is not None:
        raise ConflictError("That user is already a member of this account.")

    # Reuse existing pending invite, or create a new one
    res = await db.execute(
        select(Invitation).where(
            Invitation.account_id == account_id,
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.deleted_at.is_(None),
        )
    )
    invite = res.scalar_one_or_none()
    if invite is None:
        invite = Invitation(
            account_id=account_id,
            email=email,
            role=role,
            invited_by_user_id=invited_by.id,
        )
        db.add(invite)
    else:
        invite.role = role
        invite.invited_by_user_id = invited_by.id
        db.add(invite)
    await db.flush()

    token = _make_invite_token(invite.id)
    accept_url = f"{settings.frontend_base_url}/join?token={token}"
    sender_name = (invited_by.full_name or "Someone") + " via RevOS"
    send_transactional(
        to_email=email,
        subject=f"You've been invited to join a RevOS workspace",
        html=(
            f"<p>Hi,</p>"
            f"<p><strong>{sender_name}</strong> has invited you to join a workspace "
            f"as <strong>{role}</strong>.</p>"
            f'<p><a href="{accept_url}">Accept invitation</a></p>'
            f"<p>This link expires in 7 days. If you don't have a RevOS account yet, "
            f"sign up at {settings.frontend_base_url}/register using this email address.</p>"
        ),
        text=(
            f"{sender_name} invited you to join a RevOS workspace as {role}.\n"
            f"Accept: {accept_url}\n\nExpires in 7 days."
        ),
    )
    return invite, token


async def accept_invitation(
    db: AsyncSession, token: str, user: AdminUser
) -> Membership:
    """Exchange a signed token for a membership.

    The logged-in user's email must match the invitation email — prevents
    forwarding the link to a different person.
    """
    try:
        data = read_signed_token(token, salt=_INVITE_SALT, max_age_seconds=_INVITE_MAX_AGE)
    except AuthError as exc:
        raise PermissionError_("Invitation link is invalid or has expired.") from exc

    invite = await db.get(Invitation, uuid.UUID(str(data["iid"])))
    if invite is None or invite.deleted_at is not None:
        raise NotFoundError("Invitation not found or has been revoked.")
    if invite.accepted_at is not None:
        raise ConflictError("This invitation has already been used.")
    if user.email.lower() != invite.email.lower():
        raise PermissionError_(
            "This invitation was sent to a different email address. "
            "Please sign in with the invited email."
        )

    # Idempotent: already a member → just mark accepted and return existing
    res = await db.execute(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.account_id == invite.account_id,
            Membership.deleted_at.is_(None),
        )
    )
    existing = res.scalar_one_or_none()
    if existing is not None:
        invite.accepted_at = utcnow()
        db.add(invite)
        await db.flush()
        return existing

    membership = Membership(
        user_id=user.id,
        account_id=invite.account_id,
        role=invite.role,
    )
    invite.accepted_at = utcnow()
    db.add(membership)
    db.add(invite)
    await db.flush()
    return membership


async def revoke_invitation(
    db: AsyncSession, invite_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    invite = await db.get(Invitation, invite_id)
    if invite is None or invite.account_id != account_id or invite.deleted_at is not None:
        raise NotFoundError("Invitation not found.")
    if invite.accepted_at is not None:
        raise ConflictError("Cannot revoke an already-accepted invitation.")
    invite.deleted_at = utcnow()
    db.add(invite)
    await db.flush()


async def resend_invitation(
    db: AsyncSession, invite_id: uuid.UUID, account_id: uuid.UUID, invited_by: AdminUser
) -> tuple[Invitation, str]:
    """Re-send a pending invitation's email (refreshes the token/expiry)."""
    invite = await db.get(Invitation, invite_id)
    if invite is None or invite.account_id != account_id or invite.deleted_at is not None:
        raise NotFoundError("Invitation not found.")
    if invite.accepted_at is not None:
        raise ConflictError("This invitation has already been accepted.")
    # send_invitation reuses the existing pending row (new token, re-sends).
    return await send_invitation(db, account_id, invited_by, invite.email, invite.role)


async def list_pending_invitations(
    db: AsyncSession, account_id: uuid.UUID
) -> list[Invitation]:
    res = await db.execute(
        select(Invitation).where(
            Invitation.account_id == account_id,
            Invitation.accepted_at.is_(None),
            Invitation.deleted_at.is_(None),
        ).order_by(Invitation.created_at.asc())
    )
    return list(res.scalars().all())
