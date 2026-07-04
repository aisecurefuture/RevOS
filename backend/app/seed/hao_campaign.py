"""Seed: Hao Pan (@jhhfit) fitness-influencer social media campaign.

Creates an `influencer`-type brand, content pillars, a multi-platform social
campaign, and draft posts across TikTok / YouTube / Instagram / Facebook. All
posts are DRAFTS (copy-paste ready) — nothing is auto-published. No scraping;
links are the creator's own public profiles.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.brand import Brand, BrandType, BrandVoice
from app.models.content import ContentState, Pillar
from app.models.social import (
    SocialCampaign,
    SocialCampaignStatus,
    SocialPlatform,
    SocialPost,
)

HAO_LINKS = {
    "tiktok": "https://www.tiktok.com/@jhhfit",
    "instagram": "https://www.instagram.com/jhhfit",
    "youtube": "https://share.google/wnLLZbbZNOk8TpADL",
    "facebook": "https://www.facebook.com/share/17zRWy9ncy/",
    "linktree": "https://linktr.ee/Mrhaopan",
}

_PILLARS = ["Workouts", "Nutrition", "Transformation", "Mindset & Motivation"]

_POSTS = [
    (SocialPlatform.tiktok, "60-sec full-body finisher you can do anywhere. Save this. 🔥",
     ["fitness", "workout", "fittok", "homeworkout"]),
    (SocialPlatform.instagram, "3 high-protein meals I prep every week (under $5 each). Recipe in bio.",
     ["mealprep", "highprotein", "fitfam", "nutrition"]),
    (SocialPlatform.youtube, "My 12-week transformation — what actually moved the needle (full breakdown).",
     ["transformation", "fitnessjourney", "gym"]),
    (SocialPlatform.facebook, "Motivation is fleeting. Systems win. Here's the weekly routine I never skip.",
     ["mindset", "discipline", "fitness"]),
    (SocialPlatform.tiktok, "Stop doing crunches. Do THIS for your core instead. 👇",
     ["coreworkout", "absworkout", "fittips"]),
]


async def seed_hao_campaign(db: AsyncSession) -> dict:
    """Idempotent. Returns a small summary dict."""
    existing = (await db.execute(select(Brand).where(Brand.slug == "hao-jhhfit"))).scalar_one_or_none()
    if existing is not None:
        return {"brand_id": str(existing.id), "created": False}

    brand = Brand(
        name="Hao Pan (@jhhfit)", slug="hao-jhhfit", brand_type=BrandType.influencer,
        website_url=HAO_LINKS["linktree"], tagline="Fitness, nutrition & transformation",
        description="Fitness creator @jhhfit — workouts, nutrition, and transformation content.",
        settings={"links": HAO_LINKS, "automation_enabled": False},
    )
    db.add(brand)
    await db.flush()

    db.add(BrandVoice(
        brand_id=brand.id, tone="energetic, motivational, practical, no-fluff",
        do_list=["lead with a hook", "give one actionable tip", "keep it short"],
        dont_list=["overpromise", "shame the viewer", "use jargon"],
        value_props=["sustainable fitness", "simple nutrition", "real transformation"],
    ))
    for name in _PILLARS:
        db.add(Pillar(brand_id=brand.id, name=name))

    campaign = SocialCampaign(
        brand_id=brand.id, name="Hao Fitness Growth Campaign",
        objective="Grow followers and drive Linktree clicks across platforms",
        theme="Sustainable fitness, simple nutrition, real results",
        platforms=["tiktok", "instagram", "youtube", "facebook"],
        status=SocialCampaignStatus.active,
        settings={"cta": HAO_LINKS["linktree"]},
    )
    db.add(campaign)
    await db.flush()

    for platform, caption, hashtags in _POSTS:
        db.add(SocialPost(
            brand_id=brand.id, social_campaign_id=campaign.id, platform=platform,
            caption=caption, hashtags=hashtags, state=ContentState.draft,
        ))
    await db.flush()
    return {"brand_id": str(brand.id), "created": True, "posts": len(_POSTS)}
