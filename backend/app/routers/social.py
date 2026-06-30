"""Social accounts, campaigns, posts, and draft-safe publishing."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.audit import write_audit
from app.deps import DbSession, require_admin, require_authenticated, require_editor, verify_csrf
from app.models.social import SocialAccount, SocialCampaign, SocialPost
from app.models.user import AdminUser
from app.schemas.content import (
    PublishResult,
    SocialAccountCreate,
    SocialAccountOut,
    SocialCampaignCreate,
    SocialCampaignOut,
    SocialPostCreate,
    SocialPostOut,
)
from app.services import social_service
from app.services.social.base import adapter_status

router = APIRouter(prefix="/social", tags=["social"])


@router.get("/status")
async def status(_user: Annotated[AdminUser, Depends(require_authenticated)]) -> dict:
    """Which platforms have live credentials (others are draft/copy-paste only)."""
    return {"adapters": adapter_status()}


# --- Accounts ---------------------------------------------------------------
@router.get("/accounts", response_model=list[SocialAccountOut])
async def list_accounts(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
) -> list[SocialAccount]:
    return await social_service.list_accounts(db, brand_id)


@router.post("/accounts", response_model=SocialAccountOut, status_code=201)
async def create_account(
    body: SocialAccountCreate,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> SocialAccount:
    return await social_service.create_account(db, body.model_dump())


# --- Campaigns --------------------------------------------------------------
@router.get("/campaigns", response_model=list[SocialCampaignOut])
async def list_campaigns(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
) -> list[SocialCampaign]:
    return await social_service.list_campaigns(db, brand_id)


@router.post("/campaigns", response_model=SocialCampaignOut, status_code=201)
async def create_campaign(
    body: SocialCampaignCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> SocialCampaign:
    campaign = await social_service.create_campaign(db, body.model_dump())
    await write_audit(db, action="social_campaign.create", user_id=user.id,
                      entity_type="social_campaign", entity_id=str(campaign.id), request=request)
    return campaign


# --- Posts ------------------------------------------------------------------
@router.get("/posts", response_model=list[SocialPostOut])
async def list_posts(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
    social_campaign_id: uuid.UUID | None = None,
) -> list[SocialPost]:
    return await social_service.list_posts(
        db, brand_id=brand_id, social_campaign_id=social_campaign_id)


@router.post("/posts", response_model=SocialPostOut, status_code=201)
async def create_post(
    body: SocialPostCreate,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> SocialPost:
    return await social_service.create_post(db, body.model_dump())


@router.post("/posts/{post_id}/publish", response_model=PublishResult)
async def publish_post(
    post_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_admin)],
    _: None = Depends(verify_csrf),
) -> PublishResult:
    post = await social_service.get_post_or_404(db, post_id)
    result = await social_service.publish_post(db, post)
    await write_audit(db, action="social.publish", user_id=user.id,
                      entity_type="social_post", entity_id=str(post_id),
                      request=request, meta={"mode": result["mode"]})
    return PublishResult(**result)
