"""Live insights ingestion (Phase 6) — pull real follower/engagement stats
from a creator's connected accounts into Creator.follower_count/
engagement_rate, so the marketplace, reputation, and insight dashboards
reflect real numbers instead of manual entry.

Gated by ``settings.live_insights_ingestion_enabled`` (an env flag) — the
Celery beat task is always registered, but ``ingest_all`` no-ops until the
flag is on, mirroring the social-comment-replies feature. Per-platform
adapters that can't (yet) fetch stats under the app's current API access
(TikTok/Threads engagement, LinkedIn entirely) return partial/empty
``AudienceStats`` rather than erroring, so flipping the flag on is safe even
before every platform clears App Review.

Demographics are deliberately NOT auto-updated here — merging per-platform
audience breakdowns into one dict safely is a harder problem than follower/
engagement aggregation, and a wrong auto-merge would silently corrupt data a
creator entered by hand. That stays manual for now.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.models.base import utcnow
from app.models.matching import AudienceSource, Creator, CreatorStatus
from app.models.social import SocialPlatform
from app.models.social_connection import SocialConnection, SocialConnectionStatus
from app.services import secrets_service
from app.services.industry_taxonomy import size_tier_for
from app.services.social.base import AudienceStats

logger = logging.getLogger("revos.matching.live_insights")


async def _token_data(conn: SocialConnection) -> dict | None:
    return await secrets_service.get_secret(conn.token_ref)


async def _fetch_for_connection(conn: SocialConnection) -> AudienceStats | None:
    token = await _token_data(conn)
    if token is None:
        return None

    from app.services import social_connection_service as scs
    from app.services.social import meta as meta_client
    from app.services.social import tiktok as tiktok_client
    from app.services.social import threads as threads_client
    from app.services.social import x as x_client
    from app.services.social import youtube as youtube_client

    try:
        if conn.platform == SocialPlatform.facebook:
            return await meta_client.get_page_audience_stats(token["page_id"], token["access_token"])
        if conn.platform == SocialPlatform.instagram:
            return await meta_client.get_instagram_audience_stats(token["ig_user_id"], token["access_token"])
        if conn.platform == SocialPlatform.threads:
            return await threads_client.get_audience_stats(token.get("threads_user_id", conn.external_id),
                                                            token["access_token"])
        if conn.platform == SocialPlatform.youtube:
            access_token = await scs._youtube_access_token(conn, token)
            return await youtube_client.get_audience_stats(access_token)
        if conn.platform == SocialPlatform.tiktok:
            access_token = await scs._tiktok_access_token(conn, token)
            return await tiktok_client.get_audience_stats(access_token)
        if conn.platform == SocialPlatform.twitter:
            access_token = await scs._x_access_token(conn, token)
            return await x_client.get_audience_stats(access_token)
        if conn.platform == SocialPlatform.linkedin:
            return None   # documented no-op; see linkedin.get_audience_stats
    except Exception:  # noqa: BLE001 — one platform's failure must not block others
        logger.warning("Live insights fetch failed for connection %s (%s)",
                       conn.id, conn.platform, exc_info=True)
        return None
    return None


async def ingest_for_creator(db: AsyncSession, creator: Creator) -> dict:
    """Fetch stats across every active connection linked to this creator and
    aggregate them onto the Creator row. Returns a small summary dict."""
    conns = (await db.execute(select(SocialConnection).where(
        SocialConnection.creator_id == creator.id,
        SocialConnection.status == SocialConnectionStatus.active,
        SocialConnection.deleted_at.is_(None),
    ))).scalars().all()
    if not conns:
        return {"updated": False, "platforms": 0}

    results: list[AudienceStats] = []
    for conn in conns:
        stats = await _fetch_for_connection(conn)
        if stats is not None and stats.follower_count is not None:
            results.append(stats)

    if not results:
        return {"updated": False, "platforms": 0}

    total_followers = sum(r.follower_count for r in results)
    weighted = [(r.engagement_rate, r.follower_count) for r in results if r.engagement_rate is not None]
    engagement_rate = (
        sum(rate * weight for rate, weight in weighted) / sum(weight for _, weight in weighted)
        if weighted else None
    )

    creator.follower_count = total_followers
    if engagement_rate is not None:
        creator.engagement_rate = engagement_rate
    creator.size_tier = size_tier_for(total_followers)
    creator.audience_source = AudienceSource.connected
    creator.audience_captured_at = utcnow()
    db.add(creator)
    await db.flush()
    return {"updated": True, "platforms": len(results), "follower_count": total_followers}


async def ingest_all(db: AsyncSession) -> dict:
    if not settings.live_insights_ingestion_enabled:
        return {"enabled": False, "creators_checked": 0, "creators_updated": 0}

    creator_ids = (await db.execute(
        select(SocialConnection.creator_id).where(
            SocialConnection.creator_id.is_not(None),
            SocialConnection.status == SocialConnectionStatus.active,
            SocialConnection.deleted_at.is_(None),
        ).distinct()
    )).scalars().all()

    checked = updated = 0
    for creator_id in creator_ids:
        creator = await db.get(Creator, creator_id)
        if creator is None or creator.deleted_at is not None or creator.status != CreatorStatus.active:
            continue
        checked += 1
        result = await ingest_for_creator(db, creator)
        if result["updated"]:
            updated += 1
    await db.flush()
    return {"enabled": True, "creators_checked": checked, "creators_updated": updated}
