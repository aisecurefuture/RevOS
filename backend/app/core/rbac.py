"""Role-based access control.

Roles are ordered: viewer < editor < admin < owner. Capability helpers express
intent (who can send, who can approve) so routers read clearly. Sensitive
marketing actions (sending, approving, importing) require admin or owner.
"""

from __future__ import annotations

from app.models.user import Role

# Higher number = more privilege.
_ROLE_RANK: dict[Role, int] = {
    Role.viewer: 0,
    Role.editor: 1,
    Role.admin: 2,
    Role.owner: 3,
}


def role_rank(role: Role) -> int:
    return _ROLE_RANK.get(role, 0)


def role_at_least(role: Role, required: Role) -> bool:
    return role_rank(role) >= role_rank(required)


# --- Capability helpers (semantic, used by routers/services) ----------------
def can_edit_content(role: Role) -> bool:
    """Create/edit drafts and content."""
    return role_at_least(role, Role.editor)


def can_send_email(role: Role) -> bool:
    """Trigger outbound email / bulk sends (admin+)."""
    return role_at_least(role, Role.admin)


def can_approve(role: Role) -> bool:
    """Approve campaigns, sequences, publishes, AI-applied changes (admin+)."""
    return role_at_least(role, Role.admin)


def can_manage_integrations(role: Role) -> bool:
    """View/rotate integration secrets, manage users (owner only)."""
    return role_at_least(role, Role.owner)
