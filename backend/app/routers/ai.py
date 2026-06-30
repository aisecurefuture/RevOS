"""AI-assisted drafting. Every endpoint returns a DRAFT for human review —
nothing is auto-sent or auto-published. Editor role + CSRF + AI rate limit.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.config import settings
from app.core.rate_limit import rate_limit
from app.deps import DbSession, require_editor, verify_csrf
from app.models.user import AdminUser
from app.schemas.ai import (
    AIStatus,
    BrandRef,
    DraftEmailRequest,
    DraftResult,
    DraftSocialRequest,
    LandingCopyRequest,
    LeadMagnetRequest,
)
from app.services import ai_service, analytics_service, brand_service
from app.services.brand_service import get_brand_or_404

router = APIRouter(prefix="/ai", tags=["ai"])

_ai_limit = rate_limit("ai", settings.ai_rate_limit)
EditorUser = Annotated[AdminUser, Depends(require_editor)]


async def _voice(db, brand_id) -> str | None:
    voice = await brand_service.get_voice(db, brand_id)
    return voice.tone if voice else None


@router.get("/status", response_model=AIStatus)
async def status(_user: EditorUser) -> AIStatus:
    return AIStatus(available=ai_service.ai_available(), provider=settings.ai_provider)


@router.post("/draft-email", response_model=DraftResult)
async def draft_email(
    body: DraftEmailRequest, db: DbSession, _user: EditorUser,
    _rl: None = Depends(_ai_limit), _c: None = Depends(verify_csrf),
) -> DraftResult:
    brand = await get_brand_or_404(db, body.brand_id)
    result = ai_service.draft_email(
        brand_name=brand.name, voice=await _voice(db, brand.id),
        goal=body.goal, audience=body.audience)
    return DraftResult(text=result.text, source=result.source)


@router.post("/draft-social", response_model=DraftResult)
async def draft_social(
    body: DraftSocialRequest, db: DbSession, _user: EditorUser,
    _rl: None = Depends(_ai_limit), _c: None = Depends(verify_csrf),
) -> DraftResult:
    brand = await get_brand_or_404(db, body.brand_id)
    result = ai_service.draft_social(
        brand_name=brand.name, platform=body.platform, topic=body.topic,
        voice=await _voice(db, brand.id))
    return DraftResult(text=result.text, source=result.source)


@router.post("/landing-copy", response_model=DraftResult)
async def landing_copy(
    body: LandingCopyRequest, db: DbSession, _user: EditorUser,
    _rl: None = Depends(_ai_limit), _c: None = Depends(verify_csrf),
) -> DraftResult:
    brand = await get_brand_or_404(db, body.brand_id)
    result = ai_service.landing_copy(
        brand_name=brand.name, offer=body.offer, audience=body.audience)
    return DraftResult(text=result.text, source=result.source)


@router.post("/lead-magnet-ideas", response_model=DraftResult)
async def lead_magnet_ideas(
    body: LeadMagnetRequest, db: DbSession, _user: EditorUser,
    _rl: None = Depends(_ai_limit), _c: None = Depends(verify_csrf),
) -> DraftResult:
    brand = await get_brand_or_404(db, body.brand_id)
    result = ai_service.lead_magnet_ideas(
        brand_name=brand.name, audience=body.audience, count=body.count)
    return DraftResult(text=result.text, source=result.source)


@router.post("/summarize-campaign", response_model=DraftResult)
async def summarize_campaign(
    body: BrandRef, db: DbSession, _user: EditorUser,
    _rl: None = Depends(_ai_limit), _c: None = Depends(verify_csrf),
) -> DraftResult:
    overview = await analytics_service.overview(db, body.brand_id)
    data = (f"Revenue MTD (cents): {overview['revenue_mtd_cents']}\n"
            f"New leads (30d): {overview['new_leads_30d']}\n"
            f"Subscribers: {overview['subscribers']}\n"
            f"Pipeline value (cents): {overview['pipeline_value_cents']}\n"
            f"Email sent: {overview['email']['sent']}, "
            f"open rate: {overview['email']['open_rate']}")
    result = ai_service.summarize(title="Campaign performance", data=data)
    return DraftResult(text=result.text, source=result.source)
