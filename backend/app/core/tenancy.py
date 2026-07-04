"""Tenant isolation engine (Phase 2 M1).

Every ``TenantModel`` row carries an ``account_id``. Two mechanisms keep tenants
isolated automatically, so no query or insert can leak across accounts by
forgetting to scope:

- **Reads** — the shared CRUD chokepoints (`crud.get_active` / `list_active`)
  call `scope_stmt()`, which adds ``account_id == active`` to the statement.
- **Writes** — a ``before_flush`` hook stamps ``account_id`` on any new
  TenantModel row from the request's active account. So even a row created with
  another tenant's ``brand_id`` still belongs to the caller's account.

The active account lives in a contextvar set by the auth dependency. When it's
unset (public endpoints, Celery jobs, the data migration) no filter is applied
and inserts are left unstamped — those paths must resolve their own account
(e.g. a public form submission stamps the form's brand's account explicitly).
"""

from __future__ import annotations

import contextvars
import uuid

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models.base import TenantModel

_active_account: contextvars.ContextVar[uuid.UUID | None] = contextvars.ContextVar(
    "revos_active_account", default=None
)


def set_active_account(account_id: uuid.UUID | None):
    """Set the active account for this request/task. Returns a reset token."""
    return _active_account.set(account_id)


def reset_active_account(token) -> None:
    _active_account.reset(token)


def get_active_account() -> uuid.UUID | None:
    return _active_account.get()


def is_tenant_scoped(model: type) -> bool:
    """True for tenant-owned tables (explicit via the TenantModel base — NOT via
    the mere presence of an account_id column, which Membership also has)."""
    return isinstance(model, type) and issubclass(model, TenantModel)


def scope_stmt(stmt, model: type, account_id: uuid.UUID):
    """Filter a SELECT to a single account."""
    return stmt.where(model.account_id == account_id)  # type: ignore[attr-defined]


@event.listens_for(Session, "before_flush")
def _stamp_tenant_writes(session: Session, flush_context, instances) -> None:
    """Stamp account_id on new tenant rows from the active account. Rows created
    without an active account (system/migration paths) are left as-is."""
    account_id = _active_account.get()
    if account_id is None:
        return
    for obj in session.new:
        if isinstance(obj, TenantModel) and getattr(obj, "account_id", None) is None:
            obj.account_id = account_id
