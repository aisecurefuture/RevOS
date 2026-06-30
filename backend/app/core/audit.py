"""Audit log writer.

Every privileged/admin action should call ``write_audit`` so there is an
append-only trail (OWASP "Security Logging & Monitoring Failures"). Never pass
secrets in ``meta``.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.net import client_ip as _net_client_ip
from app.models.user import AuditLog


def _client_ip(request: Request | None) -> str | None:
    return _net_client_ip(request) if request is not None else None


async def write_audit(
    db: AsyncSession,
    *,
    action: str,
    user_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    request: Request | None = None,
    meta: dict | None = None,
) -> AuditLog:
    log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_address=_client_ip(request),
        user_agent=(request.headers.get("user-agent", "")[:400] if request else None),
        meta=meta or {},
    )
    db.add(log)
    await db.flush()
    return log
