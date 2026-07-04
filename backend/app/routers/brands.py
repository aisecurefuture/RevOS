"""Brand CRUD plus nested audiences, buyer personas, and brand voice.

Brand create/update/delete require admin; sub-resources (audiences, personas,
voice) require editor. Reads require any authenticated user. All mutations are
CSRF-protected and audit-logged.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import write_audit
from app.deps import (
    DbSession,
    require_admin,
    require_authenticated,
    require_editor,
    verify_csrf,
)
from app.models.brand import Audience, Brand, BuyerPersona
from app.models.user import AdminUser
from app.schemas.brand import (
    AudienceCreate,
    AudienceOut,
    AudienceUpdate,
    BrandCreate,
    BrandDetailOut,
    BrandOut,
    BrandUpdate,
    BrandVoiceOut,
    BrandVoiceUpsert,
    PersonaCreate,
    PersonaOut,
    PersonaUpdate,
)
from app.schemas.common import Message
from app.services import brand_service
from app.services.crud import get_active, list_active, soft_delete

router = APIRouter(prefix="/brands", tags=["brands"])


# --- Brands -----------------------------------------------------------------
@router.get("", response_model=list[BrandOut])
async def list_brands(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    active_only: bool = True,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Brand]:
    filters = [Brand.is_active.is_(True)] if active_only else []
    return await list_active(db, Brand, filters=filters, limit=limit, offset=offset)


@router.post("", response_model=BrandOut, status_code=201)
async def create_brand(
    body: BrandCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_admin)],
    _: None = Depends(verify_csrf),
) -> Brand:
    brand = await brand_service.create_brand(db, body)
    await write_audit(db, action="brand.create", user_id=user.id,
                      entity_type="brand", entity_id=str(brand.id), request=request)
    return brand


@router.get("/{brand_id}", response_model=BrandDetailOut)
async def get_brand(
    brand_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> BrandDetailOut:
    brand = await get_active(db, Brand, brand_id)
    detail = BrandDetailOut.model_validate(brand)
    detail.audiences = [
        AudienceOut.model_validate(a) for a in await brand_service.list_audiences(db, brand_id)
    ]
    detail.personas = [
        PersonaOut.model_validate(p) for p in await brand_service.list_personas(db, brand_id)
    ]
    voice = await brand_service.get_voice(db, brand_id)
    detail.voice = BrandVoiceOut.model_validate(voice) if voice else None
    return detail


@router.patch("/{brand_id}", response_model=BrandOut)
async def update_brand(
    brand_id: uuid.UUID,
    body: BrandUpdate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_admin)],
    _: None = Depends(verify_csrf),
) -> Brand:
    brand = await get_active(db, Brand, brand_id)
    brand = await brand_service.update_brand(db, brand, body)
    await write_audit(db, action="brand.update", user_id=user.id,
                      entity_type="brand", entity_id=str(brand_id), request=request)
    return brand


@router.delete("/{brand_id}", response_model=Message)
async def delete_brand(
    brand_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_admin)],
    _: None = Depends(verify_csrf),
) -> Message:
    brand = await get_active(db, Brand, brand_id)
    await soft_delete(db, brand)
    await write_audit(db, action="brand.delete", user_id=user.id,
                      entity_type="brand", entity_id=str(brand_id), request=request)
    return Message(status="deleted")


# --- Audiences --------------------------------------------------------------
@router.get("/{brand_id}/audiences", response_model=list[AudienceOut])
async def list_audiences(
    brand_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> list[Audience]:
    await get_active(db, Brand, brand_id)
    return await brand_service.list_audiences(db, brand_id)


@router.post("/{brand_id}/audiences", response_model=AudienceOut, status_code=201)
async def create_audience(
    brand_id: uuid.UUID,
    body: AudienceCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Audience:
    await get_active(db, Brand, brand_id)
    audience = await brand_service.create_audience(db, brand_id, body)
    await write_audit(db, action="audience.create", user_id=user.id,
                      entity_type="audience", entity_id=str(audience.id), request=request)
    return audience


@router.patch("/audiences/{audience_id}", response_model=AudienceOut)
async def update_audience(
    audience_id: uuid.UUID,
    body: AudienceUpdate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Audience:
    audience = await get_active(db, Audience, audience_id)
    audience = await brand_service.update_audience(db, audience, body)
    await write_audit(db, action="audience.update", user_id=user.id,
                      entity_type="audience", entity_id=str(audience_id), request=request)
    return audience


@router.delete("/audiences/{audience_id}", response_model=Message)
async def delete_audience(
    audience_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Message:
    audience = await get_active(db, Audience, audience_id)
    await soft_delete(db, audience)
    await write_audit(db, action="audience.delete", user_id=user.id,
                      entity_type="audience", entity_id=str(audience_id), request=request)
    return Message(status="deleted")


# --- Buyer personas ---------------------------------------------------------
@router.get("/{brand_id}/personas", response_model=list[PersonaOut])
async def list_personas(
    brand_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> list[BuyerPersona]:
    await get_active(db, Brand, brand_id)
    return await brand_service.list_personas(db, brand_id)


@router.post("/{brand_id}/personas", response_model=PersonaOut, status_code=201)
async def create_persona(
    brand_id: uuid.UUID,
    body: PersonaCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> BuyerPersona:
    await get_active(db, Brand, brand_id)
    persona = await brand_service.create_persona(db, brand_id, body)
    await write_audit(db, action="persona.create", user_id=user.id,
                      entity_type="persona", entity_id=str(persona.id), request=request)
    return persona


@router.patch("/personas/{persona_id}", response_model=PersonaOut)
async def update_persona(
    persona_id: uuid.UUID,
    body: PersonaUpdate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> BuyerPersona:
    persona = await get_active(db, BuyerPersona, persona_id)
    persona = await brand_service.update_persona(db, persona, body)
    await write_audit(db, action="persona.update", user_id=user.id,
                      entity_type="persona", entity_id=str(persona_id), request=request)
    return persona


@router.delete("/personas/{persona_id}", response_model=Message)
async def delete_persona(
    persona_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Message:
    persona = await get_active(db, BuyerPersona, persona_id)
    await soft_delete(db, persona)
    await write_audit(db, action="persona.delete", user_id=user.id,
                      entity_type="persona", entity_id=str(persona_id), request=request)
    return Message(status="deleted")


# --- Brand voice ------------------------------------------------------------
@router.get("/{brand_id}/voice", response_model=BrandVoiceOut | None)
async def get_voice(
    brand_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> BrandVoiceOut | None:
    voice = await brand_service.get_voice(db, brand_id)
    return BrandVoiceOut.model_validate(voice) if voice else None


@router.put("/{brand_id}/voice", response_model=BrandVoiceOut)
async def upsert_voice(
    brand_id: uuid.UUID,
    body: BrandVoiceUpsert,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> BrandVoiceOut:
    await get_active(db, Brand, brand_id)
    voice = await brand_service.upsert_voice(db, brand_id, body)
    await write_audit(db, action="brand_voice.upsert", user_id=user.id,
                      entity_type="brand_voice", entity_id=str(brand_id), request=request)
    return BrandVoiceOut.model_validate(voice)
