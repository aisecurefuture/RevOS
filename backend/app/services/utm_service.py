"""UTM link builder + click tracking (privacy-friendly short links)."""

from __future__ import annotations

import secrets
import uuid
from urllib.parse import urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.models.analytics import UTMLink
from app.services.crud import list_active

_UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content")


async def _unique_code(db: AsyncSession) -> str:
    for _ in range(10):
        code = secrets.token_urlsafe(6)[:8]
        exists = await db.execute(select(UTMLink).where(UTMLink.short_code == code))
        if exists.scalar_one_or_none() is None:
            return code
    return secrets.token_urlsafe(10)[:12]


async def create_link(db: AsyncSession, data: dict) -> UTMLink:
    code = await _unique_code(db)
    link = UTMLink(short_code=code, **data)
    db.add(link)
    await db.flush()
    await db.refresh(link)
    return link


async def get_by_code(db: AsyncSession, code: str) -> UTMLink | None:
    result = await db.execute(
        select(UTMLink).where(UTMLink.short_code == code, UTMLink.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


def build_target(link: UTMLink) -> str:
    """Append the link's UTM params to its target URL."""
    params = {k: getattr(link, k) for k in _UTM_KEYS if getattr(link, k)}
    parsed = urlparse(link.target_url)
    existing = parsed.query
    query = (existing + "&" if existing else "") + urlencode(params) if params else existing
    return urlunparse(parsed._replace(query=query))


async def track_click(db: AsyncSession, link: UTMLink) -> str:
    link.click_count += 1
    db.add(link)
    await db.flush()
    return build_target(link)


def short_url(link: UTMLink) -> str:
    return f"{settings.public_base_url}/api/public/u/{link.short_code}"


async def list_links(
    db: AsyncSession, brand_id: uuid.UUID | None, limit: int = 100
) -> list[UTMLink]:
    filters = [UTMLink.brand_id == brand_id] if brand_id else []
    return await list_active(db, UTMLink, filters=filters, limit=limit)
