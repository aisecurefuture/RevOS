"""Content autopilot (Phase 3) — generate → gate → (auto-)publish.

Ties together the pieces already built:
  * ai_service — grounded generation (local Ollama or any configured provider).
  * brand_book_service — the grounding pack (source of truth) and the accuracy
    gate (banned terms / ungrounded stats / disclaimers).
  * social_connection_service + automation_service — submit for approval and,
    when hands-off is on, execute the publish.

Safety is structural: only content that passes the Brand Book gate cleanly is
ever auto-published. Blocked content (banned term) is discarded; merely-flagged
content (e.g. an unverified statistic) is queued for a human even in full
autopilot. Autopilot also refuses to run unless the brand book is *published*.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, RevOSError
from app.core.tenancy import set_active_account
from app.models.account import Account
from app.models.autopilot import AutopilotConfig
from app.models.base import utcnow
from app.models.brand import Brand
from app.models.social_connection import SocialConnectionStatus
from app.models.user import AdminUser
from app.services import (
    ai_service,
    automation_service,
    brand_book_service,
    social_connection_service,
    social_service,
)

logger = logging.getLogger("revos.autopilot")

_MAX_POSTS_PER_RUN = 5


# ---------------------------------------------------------------------------
# Config CRUD
# ---------------------------------------------------------------------------

async def get_or_create_config(db: AsyncSession, brand_id: uuid.UUID, account_id: uuid.UUID) -> AutopilotConfig:
    result = await db.execute(
        select(AutopilotConfig).where(
            AutopilotConfig.brand_id == brand_id, AutopilotConfig.deleted_at.is_(None)
        )
    )
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = AutopilotConfig(account_id=account_id, brand_id=brand_id)
        db.add(cfg)
        await db.flush()
        await db.refresh(cfg)
    return cfg


async def update_config(
    db: AsyncSession, brand_id: uuid.UUID, account_id: uuid.UUID, user: AdminUser, data: dict
) -> AutopilotConfig:
    cfg = await get_or_create_config(db, brand_id, account_id)
    if "posts_per_run" in data and data["posts_per_run"] is not None:
        data["posts_per_run"] = max(1, min(_MAX_POSTS_PER_RUN, data["posts_per_run"]))
    for key, value in data.items():
        setattr(cfg, key, value)
    cfg.configured_by = user.id
    db.add(cfg)
    await db.flush()
    await db.refresh(cfg)
    return cfg


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

async def generate_caption(
    brand: Brand, platform: str, grounding: brand_book_service.GroundingPack,
    theme: str | None, cta: str | None,
) -> str | None:
    """Generate one on-brand caption for a platform, grounded in the brand book.
    Returns None when no AI provider is configured."""
    system = (
        f"You are an expert short-form social copywriter. Write ONE {platform} post. "
        "Lead with a scroll-stopping hook in the first line. Keep it tight and native to "
        "the platform. End with a clear call to action, then 2-4 relevant hashtags. "
        "Output ONLY the post text — no preamble, quotes, or explanation. "
        "State facts ONLY from the Approved claims in the context; never invent "
        "statistics, metrics, certifications, or facts."
    )
    context = grounding.prompt_context
    if theme:
        context += f"\n\n## Angle for this post\n{theme}"
    if cta:
        context += f"\n\n## Preferred call to action\n{cta}"
    # ai_service.generate is synchronous (provider HTTP call) — offload it so the
    # event loop isn't blocked for the on-demand API path.
    text = await asyncio.to_thread(
        ai_service.generate, system=system, context=context, max_tokens=400, use_case="social",
    )
    return text.strip() if text else None


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

async def run_for_brand(db: AsyncSession, config: AutopilotConfig) -> dict:
    """Generate, gate, and (auto-)submit content for one brand. Returns a stats
    dict: generated / published / queued / blocked / skipped."""
    stats = {"generated": 0, "published": 0, "queued": 0, "blocked": 0, "skipped": 0}

    brand = await db.get(Brand, config.brand_id)
    if brand is None or brand.deleted_at is not None:
        return stats
    account_id = brand.account_id
    set_active_account(account_id)

    grounding = await brand_book_service.assemble_grounding_context(db, config.brand_id)
    if not grounding.is_published:
        logger.info("Autopilot: brand %s book not published — skipping.", config.brand_id)
        stats["skipped"] += 1
        return stats

    actor = await _resolve_actor(db, config, account_id)
    if actor is None:
        logger.warning("Autopilot: no actor for brand %s — skipping.", config.brand_id)
        stats["skipped"] += 1
        return stats

    conns = await social_connection_service.list_connections(db, account_id)
    available = {str(c.platform) for c in conns if c.status == SocialConnectionStatus.active}
    target_platforms = [p for p in config.platforms if p in available]
    if not target_platforms:
        logger.info("Autopilot: brand %s has no connected target platforms.", config.brand_id)

    themes = config.content_themes or [None]
    idx = 0
    per_run = max(1, min(_MAX_POSTS_PER_RUN, config.posts_per_run or 1))
    for platform in target_platforms:
        for _ in range(per_run):
            theme = themes[idx % len(themes)]
            idx += 1

            caption = await generate_caption(brand, platform, grounding, theme, config.default_cta)
            if not caption:
                stats["skipped"] += 1
                continue
            stats["generated"] += 1

            check = await brand_book_service.check_content(db, config.brand_id, caption)
            if check.blocked:
                stats["blocked"] += 1
                logger.info("Autopilot blocked content for brand %s: %s", config.brand_id, check.banned_hits)
                continue

            post = await social_service.create_post(db, {
                "brand_id": config.brand_id, "platform": platform, "caption": caption,
            })
            try:
                approval = await social_connection_service.submit_for_approval(
                    db, post.id, account_id, actor,
                )
            except RevOSError:
                stats["skipped"] += 1
                continue

            # Auto-publish only fully-clean content, and only when opted in.
            if config.auto_publish and check.passed:
                try:
                    await automation_service.execute_approval(db, approval, actor)
                    stats["published"] += 1
                except RevOSError:
                    logger.exception("Autopilot publish failed for brand %s; left for review.", config.brand_id)
                    stats["queued"] += 1
            else:
                stats["queued"] += 1

    config.last_run_at = utcnow()
    db.add(config)
    await db.flush()
    return stats


async def _resolve_actor(db: AsyncSession, config: AutopilotConfig, account_id: uuid.UUID) -> AdminUser | None:
    if config.configured_by:
        actor = await db.get(AdminUser, config.configured_by)
        if actor is not None:
            return actor
    acct = await db.get(Account, account_id)
    if acct is not None:
        return await db.get(AdminUser, acct.owner_user_id)
    return None


async def run_autopilot(db: AsyncSession) -> dict:
    """Beat entry point: run every enabled brand whose cadence is due."""
    now = utcnow()
    result = await db.execute(
        select(AutopilotConfig).where(
            AutopilotConfig.enabled.is_(True), AutopilotConfig.deleted_at.is_(None)
        )
    )
    configs = list(result.scalars().all())

    totals = {"brands_run": 0, "generated": 0, "published": 0, "queued": 0, "blocked": 0}
    for config in configs:
        due = config.last_run_at is None or (
            config.last_run_at + timedelta(hours=max(1, config.run_interval_hours)) <= now
        )
        if not due:
            continue
        try:
            stats = await run_for_brand(db, config)
            totals["brands_run"] += 1
            for k in ("generated", "published", "queued", "blocked"):
                totals[k] += stats[k]
        except Exception:  # noqa: BLE001 — one brand's failure must not stop the sweep
            logger.exception("Autopilot run failed for brand %s", config.brand_id)
    return totals


async def run_now(db: AsyncSession, brand_id: uuid.UUID, account_id: uuid.UUID) -> dict:
    """On-demand run for a single brand (ignores the cadence)."""
    cfg = await get_or_create_config(db, brand_id, account_id)
    return await run_for_brand(db, cfg)
