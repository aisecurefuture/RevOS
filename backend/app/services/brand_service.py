"""Brand, audience, persona, and brand-voice service logic."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.text import clean_text, slugify
from app.models.brand import Audience, Brand, BrandVoice, BuyerPersona
from app.schemas.brand import (
    AudienceCreate,
    AudienceUpdate,
    BrandCreate,
    BrandUpdate,
    BrandVoiceUpsert,
    PersonaCreate,
    PersonaUpdate,
)
from app.services.crud import get_active, list_active, unique_slug

_TEXT_FIELDS = {"name", "tagline", "description", "summary", "role_title"}


def _clean(data: dict) -> dict:
    """Strip HTML from free-text fields in an update payload."""
    for field in _TEXT_FIELDS & data.keys():
        if data[field] is not None:
            data[field] = clean_text(data[field])
    return data


# --- Brand ------------------------------------------------------------------
async def create_brand(db: AsyncSession, body: BrandCreate) -> Brand:
    from app.core.tenancy import get_active_account

    base = slugify(body.slug or body.name)
    slug = await unique_slug(db, Brand, base)
    brand = Brand(
        account_id=get_active_account(),  # tenant owner (set by the auth context)
        name=clean_text(body.name) or body.name,
        slug=slug,
        brand_type=body.brand_type,
        website_url=body.website_url,
        tagline=clean_text(body.tagline),
        description=clean_text(body.description),
        logo_url=body.logo_url,
        primary_color=body.primary_color,
        settings=body.settings,
    )
    db.add(brand)
    await db.flush()
    await db.refresh(brand)
    return brand


async def update_brand(db: AsyncSession, brand: Brand, body: BrandUpdate) -> Brand:
    data = _clean(body.model_dump(exclude_unset=True))
    for key, value in data.items():
        setattr(brand, key, value)
    db.add(brand)
    await db.flush()
    await db.refresh(brand)
    return brand


# --- Audiences --------------------------------------------------------------
async def list_audiences(db: AsyncSession, brand_id: uuid.UUID) -> list[Audience]:
    return await list_active(db, Audience, filters=[Audience.brand_id == brand_id])


async def create_audience(
    db: AsyncSession, brand_id: uuid.UUID, body: AudienceCreate
) -> Audience:
    audience = Audience(
        brand_id=brand_id,
        name=clean_text(body.name) or body.name,
        description=clean_text(body.description),
        segment_rules=body.segment_rules,
        size_estimate=body.size_estimate,
    )
    db.add(audience)
    await db.flush()
    await db.refresh(audience)
    return audience


async def update_audience(
    db: AsyncSession, audience: Audience, body: AudienceUpdate
) -> Audience:
    for key, value in _clean(body.model_dump(exclude_unset=True)).items():
        setattr(audience, key, value)
    db.add(audience)
    await db.flush()
    await db.refresh(audience)
    return audience


# --- Buyer personas ---------------------------------------------------------
async def list_personas(db: AsyncSession, brand_id: uuid.UUID) -> list[BuyerPersona]:
    return await list_active(db, BuyerPersona, filters=[BuyerPersona.brand_id == brand_id])


async def create_persona(
    db: AsyncSession, brand_id: uuid.UUID, body: PersonaCreate
) -> BuyerPersona:
    persona = BuyerPersona(
        brand_id=brand_id,
        name=clean_text(body.name) or body.name,
        role_title=clean_text(body.role_title),
        summary=clean_text(body.summary),
        goals=body.goals,
        pain_points=body.pain_points,
        objections=body.objections,
        channels=body.channels,
        demographics=body.demographics,
    )
    db.add(persona)
    await db.flush()
    await db.refresh(persona)
    return persona


async def update_persona(
    db: AsyncSession, persona: BuyerPersona, body: PersonaUpdate
) -> BuyerPersona:
    for key, value in _clean(body.model_dump(exclude_unset=True)).items():
        setattr(persona, key, value)
    db.add(persona)
    await db.flush()
    await db.refresh(persona)
    return persona


# --- Brand voice (1:1) ------------------------------------------------------
async def get_voice(db: AsyncSession, brand_id: uuid.UUID) -> BrandVoice | None:
    result = await db.execute(
        select(BrandVoice).where(
            BrandVoice.brand_id == brand_id, BrandVoice.deleted_at.is_(None)
        )
    )
    return result.scalar_one_or_none()


async def upsert_voice(
    db: AsyncSession, brand_id: uuid.UUID, body: BrandVoiceUpsert
) -> BrandVoice:
    voice = await get_voice(db, brand_id)
    data = body.model_dump()
    data["style_notes"] = clean_text(data.get("style_notes"))
    if voice is None:
        voice = BrandVoice(brand_id=brand_id, **data)
    else:
        for key, value in data.items():
            setattr(voice, key, value)
    db.add(voice)
    await db.flush()
    await db.refresh(voice)
    return voice


async def get_brand_or_404(db: AsyncSession, brand_id: uuid.UUID) -> Brand:
    return await get_active(db, Brand, brand_id)
