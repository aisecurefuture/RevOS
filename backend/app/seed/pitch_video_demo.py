"""Pitch Video Studio acceptance-test seed: CyberArmor.AI investor briefing.

Idempotent: reuses the existing "cyberarmor" brand (seeded by
``app.seed.brands``) if present, creating a minimal one if not, then merges in
its design tokens (never overwrites unrelated Brand fields). Run with:

    python -m app.seed.pitch_video_demo

Requires PITCH_VIDEO_STUDIO_ENABLED=true and PITCH_VIDEO_DEFAULT_VOICE (or a
"voice" in the deck below) to actually create the job — see
deploy/pitch-video/README.md for the full run instructions.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand, BrandType

logger = logging.getLogger("revos.seed.pitch_video_demo")

CYBERARMOR_SLUG = "cyberarmor"

DESIGN_TOKENS = {
    "colors": {
        "bg_dark": "#0B0E17",
        "bg_light": "#F5F4F0",
        "surface": "#F5F4F0",
        "card": "#FFFFFF",
        "text": "#14171F",
        "muted": "#6E7280",
        "muted_on_dark": "#AEB4BF",
        "hairline": "#E0DFD8",
        "hairline_on_dark": "#2A2F3E",
        "accent": "#E5643C",
        "chart_ramp": ["#C7C5BC", "#8A8F9A", "#0B0E17", "#E5643C"],
    },
    "fonts": {"heading": "Arial", "body": "Arial"},
    "wordmark": "LEADING AI SOLUTIONS × CYBERARMOR.AI",
    "pillars": ["Govern", "Protect", "Prove", "Scale"],
}


async def _get_or_create_brand(db: AsyncSession, account_id) -> Brand:
    result = await db.execute(
        select(Brand).where(
            Brand.slug == CYBERARMOR_SLUG, Brand.account_id == account_id, Brand.deleted_at.is_(None),
        )
    )
    brand = result.scalar_one_or_none()
    if brand is None:
        brand = Brand(
            account_id=account_id, name="CyberArmor.ai", slug=CYBERARMOR_SLUG,
            brand_type=BrandType.company, tagline="AI security, runtime protection & AI trust",
        )
        db.add(brand)
        await db.flush()
        logger.info("Created brand '%s' (none existed).", CYBERARMOR_SLUG)
    brand.design_tokens = {**brand.design_tokens, **DESIGN_TOKENS}
    db.add(brand)
    await db.flush()
    await db.refresh(brand)
    return brand


def cyberarmor_deck_spec() -> dict:
    """The literal 12-scene investor deck from the Pitch Video Studio brief."""
    return {
        "brandId": CYBERARMOR_SLUG,
        "title": "CyberArmor.AI — Investor Briefing",
        "aspectRatio": "16:9",
        "voice": "",  # filled in by the caller once a real stock speaker name is confirmed
        "scenes": [
            {
                "id": "hero", "layout": "hero", "variant": "dark",
                "content": {
                    "eyebrow": "AI Trust Platform",
                    "headline": "Building the trust infrastructure for the AI economy.",
                    "sub": "Govern · Protect · Prove · Scale",
                },
                "narration": (
                    "AI is being built faster than anyone can prove it's safe. Leading AI "
                    "Solutions and CyberArmor A-I are building the trust infrastructure for the "
                    "AI economy — so organizations can govern, protect, and prove their AI with "
                    "confidence."
                ),
            },
            {
                "id": "stats", "layout": "stat-trio", "variant": "dark",
                "content": {
                    "stats": [
                        {"value": "€35M", "label": "Max EU AI Act penalty"},
                        {"value": "$15.8B", "label": "AI governance software spend by 2030"},
                        {"value": "3", "label": "Regulatory frameworks converging now"},
                    ],
                },
                "narration": (
                    "Regulation, procurement, and liability have caught up with AI. The EU AI "
                    "Act carries penalties up to thirty-five million euros. Spending on AI "
                    "governance software is projected to approach sixteen billion dollars by "
                    "2030. The question has shifted from 'can we build it' to 'can we be "
                    "trusted with it.'"
                ),
            },
            {
                "id": "problem", "layout": "statement", "variant": "light",
                "content": {
                    "text": "Every enterprise buyer now asks the same question — show us your "
                            "AI is governed and secure.",
                },
                "narration": (
                    "Every enterprise buyer now asks the same question — show us your AI is "
                    "governed and secure. Most companies can't answer it, because governance, "
                    "security, trust, and compliance live in different tools and teams."
                ),
            },
            {
                "id": "two-approaches", "layout": "two-column", "variant": "light",
                "content": {
                    "left": {"heading": "Governance alone", "body": "Documents, with no enforcement."},
                    "right": {"heading": "Security alone", "body": "Blocks attacks, but proves nothing."},
                },
                "narration": (
                    "Governance on its own is just documents, with no enforcement. Security on "
                    "its own blocks attacks but proves nothing. Trust requires both — unified."
                ),
            },
            {
                "id": "combination", "layout": "statement", "variant": "light",
                "content": {
                    "text": "One AI Trust Platform.",
                    "equation": ["Governance & advisory", "Runtime security", "AI Trust Platform"],
                },
                "narration": (
                    "So we combined them. Leading AI Solutions brings advisory and governance. "
                    "CyberArmor A-I brings the runtime security platform. Together, they form "
                    "one AI Trust Platform."
                ),
            },
            {
                "id": "architecture", "layout": "architecture", "variant": "light",
                "content": {
                    "bands": [
                        {"label": "Define policy", "description": "Set once, centrally."},
                        {"label": "Enforce at runtime", "description": "Across every AI system."},
                        {"label": "Prove continuously", "description": "A live, auditable loop."},
                    ],
                },
                "narration": (
                    "Policy is defined once, enforced at runtime across every AI system, and "
                    "proven continuously — one control plane that turns governance into a live, "
                    "auditable loop."
                ),
            },
            {
                "id": "product", "layout": "stat-trio", "variant": "dark",
                "content": {
                    "stats": [
                        {"value": "Govern", "label": "Policy, once"},
                        {"value": "Protect", "label": "Runtime enforcement"},
                        {"value": "Prove", "label": "Continuous audit"},
                    ],
                },
                "narration": (
                    "It isn't a point tool. It's an operating system for AI trust — govern, "
                    "protect, prove, and scale — in a single source of record."
                ),
            },
            {
                "id": "timeline", "layout": "timeline", "variant": "light",
                "content": {
                    "steps": [
                        {"label": "Assess"}, {"label": "Govern"}, {"label": "Deploy"},
                        {"label": "Monitor"}, {"label": "Prove"},
                    ],
                },
                "narration": (
                    "The result: in ninety days, an organization goes from exposed to "
                    "enterprise-ready — with deployed protection, continuous monitoring, and an "
                    "audit-ready trust packet."
                ),
            },
            {
                "id": "market", "layout": "stat-trio", "variant": "dark",
                "content": {
                    "stats": [
                        {"value": "$15.8B", "label": "TAM"},
                        {"value": "$4.0B", "label": "SAM"},
                        {"value": "$0.4B", "label": "SOM"},
                    ],
                },
                "narration": (
                    "This is a category being created by regulation — a total addressable "
                    "market near sixteen billion dollars, with the enterprises where AI risk "
                    "concentrates first as our beachhead."
                ),
            },
            {
                "id": "revenue", "layout": "bar-chart", "variant": "light",
                "content": {
                    "bars": [
                        {"category": "2026", "segments": [{"label": "Services", "value": 1.5}]},
                        {"category": "2027", "segments": [
                            {"label": "Services", "value": 3}, {"label": "Platform", "value": 1.5},
                        ]},
                        {"category": "2028", "segments": [
                            {"label": "Services", "value": 5}, {"label": "Platform", "value": 5},
                            {"label": "Marketplace", "value": 1},
                        ]},
                        {"category": "2029", "segments": [
                            {"label": "Services", "value": 7}, {"label": "Platform", "value": 12},
                            {"label": "Marketplace", "value": 4},
                        ]},
                        {"category": "2030", "segments": [
                            {"label": "Services", "value": 8}, {"label": "Platform", "value": 22},
                            {"label": "Marketplace", "value": 10},
                        ]},
                    ],
                    "note": "Illustrative model — not a forecast.",
                },
                "narration": (
                    "We land with services and expand into recurring platform and marketplace "
                    "revenue. On our current model — illustrative, not a forecast — that's a "
                    "path from roughly one-and-a-half million to forty million dollars in "
                    "revenue by 2030, with over seventy percent recurring."
                ),
            },
            {
                "id": "team", "layout": "team", "variant": "light",
                "content": {
                    "members": [
                        {"name": "Alan Pan", "role": "Governance & Cross-Border Strategy"},
                        {
                            "name": "Patrick Kelly", "role": "Founder, CyberArmor.AI",
                            "bio": "20+ years securing enterprise software.",
                        },
                    ],
                },
                "narration": (
                    "Governance leadership meets security engineering — Alan Pan on governance "
                    "and cross-border strategy, and Patrick Kelly, founder of CyberArmor A-I, "
                    "with over twenty years securing enterprise software."
                ),
            },
            {
                "id": "close", "layout": "close", "variant": "dark",
                "content": {
                    "headline": "Can we trust it? We're building the platform that lets you prove it.",
                    "sub": "cyberarmor.ai",
                },
                "narration": (
                    "Every organization will soon have to answer one question about its AI — "
                    "can we trust it? We're building the platform that lets them answer yes, "
                    "and prove it."
                ),
            },
        ],
    }


async def seed_pitch_video_demo(db: AsyncSession, account_id) -> dict:
    brand = await _get_or_create_brand(db, account_id)
    deck = cyberarmor_deck_spec()
    return {"brand_id": str(brand.id), "brand_slug": brand.slug, "deck_spec": deck}


async def _run() -> None:
    from app.config import settings
    from app.core.tenancy import set_active_account
    from app.database import AsyncSessionLocal, async_engine
    from app.services.account_service import list_memberships
    from app.services.auth_service import get_user_by_email

    async with AsyncSessionLocal() as db:
        owner = await get_user_by_email(db, settings.owner_email)
        if owner is None:
            raise SystemExit(f"No owner user for {settings.owner_email} — run `python -m app.seed.seed` first.")
        memberships = await list_memberships(db, owner.id)
        account_id = memberships[0].account_id
        set_active_account(account_id)

        result = await seed_pitch_video_demo(db, account_id)
        await db.commit()

    import json
    print(json.dumps(result, indent=2))
    logger.info(
        "Seeded brand '%s' (id=%s). Deck Spec printed above — paste it into "
        "Pitch Video Studio (set a real 'voice' first — see stock-speakers "
        "endpoint), or POST it directly to /api/pitch-videos.",
        result["brand_slug"], result["brand_id"],
    )
    await async_engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
