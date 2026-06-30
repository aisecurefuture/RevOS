"""Social accounts, campaigns, posts + approval-gated publishing (draft-safe)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.text import clean_text
from app.models.base import utcnow
from app.models.content import ContentState
from app.models.social import SocialAccount, SocialCampaign, SocialPost
from app.services.crud import get_active, list_active
from app.services.social.base import get_adapter


async def list_campaigns(db: AsyncSession, brand_id: uuid.UUID | None) -> list[SocialCampaign]:
    filters = [SocialCampaign.brand_id == brand_id] if brand_id else []
    return await list_active(db, SocialCampaign, filters=filters)


async def create_campaign(db: AsyncSession, data: dict) -> SocialCampaign:
    data["name"] = clean_text(data["name"]) or data["name"]
    campaign = SocialCampaign(**data)
    db.add(campaign)
    await db.flush()
    await db.refresh(campaign)
    return campaign


async def list_posts(
    db: AsyncSession, *, brand_id: uuid.UUID | None = None,
    social_campaign_id: uuid.UUID | None = None,
) -> list[SocialPost]:
    filters: list = []
    if brand_id:
        filters.append(SocialPost.brand_id == brand_id)
    if social_campaign_id:
        filters.append(SocialPost.social_campaign_id == social_campaign_id)
    return await list_active(db, SocialPost, filters=filters, limit=200)


async def create_post(db: AsyncSession, data: dict) -> SocialPost:
    post = SocialPost(**data)
    db.add(post)
    await db.flush()
    await db.refresh(post)
    return post


async def create_account(db: AsyncSession, data: dict) -> SocialAccount:
    account = SocialAccount(**data)
    account.is_connected = get_adapter(str(data["platform"])).is_configured()
    db.add(account)
    await db.flush()
    await db.refresh(account)
    return account


async def list_accounts(db: AsyncSession, brand_id: uuid.UUID | None) -> list[SocialAccount]:
    filters = [SocialAccount.brand_id == brand_id] if brand_id else []
    return await list_active(db, SocialAccount, filters=filters)


async def publish_post(db: AsyncSession, post: SocialPost) -> dict:
    """Attempt to publish via the platform adapter. With no credentials this is
    a no-op that marks the post approved/copy-paste-ready (never auto-posts)."""
    adapter = get_adapter(str(post.platform))
    outcome = adapter.publish(
        caption=post.caption, media_urls=post.media_urls, hashtags=post.hashtags
    )
    if outcome.published:
        post.state = ContentState.published
        post.published_at = utcnow()
        post.external_post_id = outcome.external_id
    else:
        # Keep as approved (ready to copy-paste) — not pushed to the platform.
        post.state = ContentState.approved
    db.add(post)
    await db.flush()
    await db.refresh(post)
    return {
        "published": outcome.published, "mode": outcome.mode,
        "message": outcome.message, "external_id": outcome.external_id,
    }


async def get_post_or_404(db: AsyncSession, post_id: uuid.UUID) -> SocialPost:
    return await get_active(db, SocialPost, post_id)
