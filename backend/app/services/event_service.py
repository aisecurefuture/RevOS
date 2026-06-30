"""First-party, privacy-friendly event tracking (IPs are hashed, never stored raw)."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import Event


def _hash_ip(ip: str | None) -> str | None:
    return hashlib.sha256(ip.encode()).hexdigest()[:64] if ip else None


async def track_event(
    db: AsyncSession,
    *,
    name: str,
    brand_id: uuid.UUID | None = None,
    properties: dict | None = None,
    lead_id: uuid.UUID | None = None,
    ip: str | None = None,
    utm: dict | None = None,
    session_id: str | None = None,
    value_cents: int | None = None,
) -> Event:
    event = Event(
        brand_id=brand_id, name=name[:120], properties=properties or {},
        lead_id=lead_id, ip_hash=_hash_ip(ip), utm=utm or {},
        session_id=(session_id or "")[:80] or None, value_cents=value_cents,
    )
    db.add(event)
    await db.flush()
    return event
