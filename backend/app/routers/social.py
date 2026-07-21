"""Social accounts, campaigns, posts, and draft-safe publishing."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from app.config import settings
from app.core.audit import write_audit
from app.core.exceptions import RevOSError
from app.deps import (
    DbSession,
    require_admin,
    require_authenticated,
    require_editor,
    verify_csrf,
)
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
from app.services import media_service, social_service
from app.services.social.base import adapter_status

_SOCIAL_MEDIA_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "video/mp4", "video/quicktime", "video/webm",
}
_SOCIAL_MEDIA_MAX_BYTES = 200 * 1024 * 1024  # 200 MB — platform caps enforced at publish

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


@router.post("/upload-media", status_code=201)
async def upload_post_media(
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    file: Annotated[UploadFile, File()],
    brand_id: Annotated[uuid.UUID, Form()],
    _: None = Depends(verify_csrf),
) -> dict:
    """Store a photo/video for attaching to a social post. Lands in the Media
    library and returns the storage key to pass in the post's media_urls."""
    ctype = file.content_type or ""
    if ctype not in _SOCIAL_MEDIA_TYPES:
        raise RevOSError(
            f"Unsupported media type {ctype!r}. Use JPEG, PNG, GIF, WebP, or MP4/MOV/WebM video.",
            code="bad_media_type", status_code=400,
        )
    data = await file.read()
    if not data:
        raise RevOSError("Empty file.", code="empty_file", status_code=400)
    if len(data) > _SOCIAL_MEDIA_MAX_BYTES:
        raise RevOSError("File too large.", code="file_too_large", status_code=400)
    asset = await media_service.create_asset(
        db, brand_id=brand_id, uploader_id=user.id,
        filename=file.filename or "upload", data=data, mime=ctype,
    )
    return {
        "media_url": asset.original_path,   # storage key — goes into media_urls
        "kind": str(asset.kind),
        "filename": asset.original_filename,
        "mime_type": asset.mime_type,
        "size_bytes": asset.size_bytes,
    }


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
