"""Landing page CRUD + public lookup. HTML bodies are sanitized on write."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.sanitize import sanitize_html
from app.core.text import clean_text, slugify
from app.models.base import utcnow
from app.models.campaign import LandingPage
from app.schemas.landing import LandingCreate, LandingUpdate
from app.services.crud import get_active, list_active, unique_slug


async def list_pages(
    db: AsyncSession, *, brand_id: uuid.UUID | None = None, limit: int = 50, offset: int = 0
) -> list[LandingPage]:
    filters = [LandingPage.brand_id == brand_id] if brand_id else []
    return await list_active(db, LandingPage, filters=filters, limit=limit, offset=offset)


async def get_page_or_404(db: AsyncSession, page_id: uuid.UUID) -> LandingPage:
    return await get_active(db, LandingPage, page_id)


async def get_published_page(db: AsyncSession, slug: str) -> LandingPage | None:
    result = await db.execute(
        select(LandingPage).where(
            LandingPage.slug == slug,
            LandingPage.is_published.is_(True),
            LandingPage.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def create_page(db: AsyncSession, body: LandingCreate) -> LandingPage:
    base = slugify(body.slug or body.title)
    slug = await unique_slug(db, LandingPage, base)
    page = LandingPage(
        brand_id=body.brand_id,
        title=clean_text(body.title) or body.title,
        slug=slug,
        template=body.template,
        headline=clean_text(body.headline),
        subheadline=clean_text(body.subheadline),
        body_html=sanitize_html(body.body_html) if body.body_html else None,
        hero_image_url=body.hero_image_url,
        cta_label=clean_text(body.cta_label),
        cta_url=body.cta_url,
        form_id=body.form_id,
        offer_id=body.offer_id,
        campaign_id=body.campaign_id,
        blocks=body.blocks,
        seo_meta=body.seo_meta,
        is_published=body.is_published,
        published_at=utcnow() if body.is_published else None,
    )
    db.add(page)
    await db.flush()
    await db.refresh(page)
    return page


async def update_page(db: AsyncSession, page: LandingPage, body: LandingUpdate) -> LandingPage:
    data = body.model_dump(exclude_unset=True)
    if "body_html" in data and data["body_html"] is not None:
        data["body_html"] = sanitize_html(data["body_html"])
    for field in ("title", "headline", "subheadline", "cta_label"):
        if field in data and data[field] is not None:
            data[field] = clean_text(data[field])
    if data.get("is_published") and page.published_at is None:
        page.published_at = utcnow()
    for key, value in data.items():
        setattr(page, key, value)
    db.add(page)
    await db.flush()
    await db.refresh(page)
    return page
