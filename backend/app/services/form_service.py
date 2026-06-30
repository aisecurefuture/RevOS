"""Form CRUD + public lookup."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.text import clean_text, slugify
from app.models.campaign import Form
from app.schemas.form import FormCreate, FormUpdate
from app.services.crud import get_active, list_active, unique_slug


async def list_forms(
    db: AsyncSession, *, brand_id: uuid.UUID | None = None, limit: int = 50, offset: int = 0
) -> list[Form]:
    filters = [Form.brand_id == brand_id] if brand_id else []
    return await list_active(db, Form, filters=filters, limit=limit, offset=offset)


async def get_form_or_404(db: AsyncSession, form_id: uuid.UUID) -> Form:
    return await get_active(db, Form, form_id)


async def get_public_form(db: AsyncSession, slug: str) -> Form | None:
    """Active, non-deleted form by slug (for public submission/rendering)."""
    result = await db.execute(
        select(Form).where(
            Form.slug == slug, Form.is_active.is_(True), Form.deleted_at.is_(None)
        )
    )
    return result.scalar_one_or_none()


async def create_form(db: AsyncSession, body: FormCreate) -> Form:
    base = slugify(body.slug or body.name)
    slug = await unique_slug(db, Form, base)
    form = Form(
        brand_id=body.brand_id,
        name=clean_text(body.name) or body.name,
        slug=slug,
        form_type=body.form_type,
        fields=[f.model_dump() for f in body.fields],
        consent_required=body.consent_required,
        consent_text=clean_text(body.consent_text),
        double_optin=body.double_optin,
        success_message=clean_text(body.success_message),
        redirect_url=body.redirect_url,
        tags_to_apply=body.tags_to_apply,
        notify_emails=[str(e) for e in body.notify_emails],
        lead_magnet_offer_id=body.lead_magnet_offer_id,
        campaign_id=body.campaign_id,
        enroll_sequence_id=body.enroll_sequence_id,
        embed_enabled=body.embed_enabled,
    )
    db.add(form)
    await db.flush()
    await db.refresh(form)
    return form


async def update_form(db: AsyncSession, form: Form, body: FormUpdate) -> Form:
    data = body.model_dump(exclude_unset=True)
    if "fields" in data and data["fields"] is not None:
        data["fields"] = [f if isinstance(f, dict) else f.model_dump() for f in data["fields"]]
    if "notify_emails" in data and data["notify_emails"] is not None:
        data["notify_emails"] = [str(e) for e in data["notify_emails"]]
    for field in ("name", "consent_text", "success_message"):
        if field in data and data[field] is not None:
            data[field] = clean_text(data[field])
    for key, value in data.items():
        setattr(form, key, value)
    db.add(form)
    await db.flush()
    await db.refresh(form)
    return form
