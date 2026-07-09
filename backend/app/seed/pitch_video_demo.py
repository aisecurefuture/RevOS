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
    "wordmark": "CYBERARMOR AI",
    "pillars": ["Inspect", "Score", "Enforce", "Prove"],
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
    """The 11-scene investor cut (~2.5-3 min) built from CyberArmor_VC_Deck_v7.

    Beat structure per the master brief: hook (second-person fear) -> stakes
    (Gartner/OWASP) -> market -> the fix as ONE gate metaphor (no architecture
    jargon) -> proof (live product, exit comps as cards) -> the blueprint
    moment ($1B framed EXACTLY as the deck does: an engineered plan with the
    revenue math on screen, never a current-value claim) -> ask -> single CTA
    (book the 15-minute PoC).

    Narration is written TTS-phonetically ("A-I", "CyberArmor dot A-I",
    "U-R-L", numbers spelled out) — XTTS mispronounces initialisms and
    figures written the on-screen way. On-screen `content` keeps proper
    branding/formatting; only `narration` uses phonetic spellings.
    """
    return {
        "brandId": CYBERARMOR_SLUG,
        "title": "CyberArmor AI — Investor Briefing (v7)",
        "aspectRatio": "16:9",
        "voice": "",  # empty -> PITCH_VIDEO_DEFAULT_VOICE; or set per render
        "scenes": [
            {
                "id": "hook", "layout": "hero", "variant": "dark",
                "content": {
                    "eyebrow": "CyberArmor AI",
                    "headline": "Your AI agents are reading the internet.",
                    "sub": "Nothing is checking what they read.",
                },
                "narration": (
                    "Your A-I agents are reading the internet. Right now. Browsers, coding "
                    "assistants, autonomous agents — pulling in pages, documents, and tool "
                    "output. And nothing is checking what they read."
                ),
            },
            {
                "id": "stakes", "layout": "stat-trio", "variant": "dark",
                "content": {
                    "stats": [
                        {"value": "25%", "label": "of enterprise breaches will trace to AI-agent abuse by 2028 — Gartner"},
                        {"value": "50%", "label": "of incident-response effort will involve AI-driven apps by 2028 — Gartner"},
                        {"value": "#1", "label": "prompt injection tops the OWASP Top 10 for LLM apps — 2025"},
                    ],
                },
                "narration": (
                    "The risk curve is bending up. Gartner projects a quarter of enterprise "
                    "breaches will trace back to A-I agent abuse by twenty twenty-eight — and "
                    "half of all incident-response effort will involve A-I driven apps. Prompt "
                    "injection already tops the industry's list of large-language-model risks."
                ),
            },
            {
                "id": "market", "layout": "stat-trio", "variant": "dark",
                "content": {
                    "stats": [
                        {"value": "$8.7B → $35.5B", "label": "Generative-AI cybersecurity market, 2025 → 2031"},
                        {"value": "8+", "label": "AI-security startups acquired by incumbents since 2024"},
                        {"value": "$1.8B+", "label": "spent by incumbents consolidating the category"},
                    ],
                },
                "narration": (
                    "And the money is bending with it. Generative A-I cybersecurity grows from "
                    "under nine billion dollars to over thirty-five billion by twenty "
                    "thirty-one. Incumbents have already made more than eight acquisitions "
                    "since twenty twenty-four. This category isn't just growing — it's "
                    "consolidating."
                ),
            },
            {
                "id": "question", "layout": "statement", "variant": "light",
                "content": {
                    "text": "Legacy filters ask \u201cis this safe for a human?\u201d "
                            "The question that matters now: is it safe for an AI to read?",
                },
                "narration": (
                    "The fix isn't another filter asking whether a page is safe for a human. "
                    "Every piece of content headed for an A-I should pass one checkpoint that "
                    "asks a different question — is this safe for an A-I to read?"
                ),
            },
            {
                "id": "gate", "layout": "architecture", "variant": "light",
                "content": {
                    "bands": [
                        {"label": "Inspect", "description": "Untrusted content is safely fetched and examined before anything reads it."},
                        {"label": "Score", "description": "Injection, phishing, hidden instructions — scored in milliseconds."},
                        {"label": "Enforce", "description": "Allow · warn · redact · block — by policy, with signed evidence."},
                    ],
                },
                "narration": (
                    "Picture a gate between the open internet and your A-I. Content flows in, "
                    "gets inspected and scored — injection, phishing, hidden instructions — "
                    "and policy decides: allow, warn, redact, or block. With signed evidence "
                    "of every decision."
                ),
            },
            {
                "id": "unowned", "layout": "statement", "variant": "light",
                "content": {
                    "text": "Everyone bought detection. Nobody owns the gate.",
                },
                "narration": (
                    "Everyone bought detection. Nobody owns the gate. Legacy filters protect "
                    "people. Point tools guard prompts. The moment of ingestion — where "
                    "content actually becomes A-I context — is unowned. That's the control "
                    "point CyberArmor takes."
                ),
            },
            {
                "id": "proof", "layout": "stat-trio", "variant": "dark",
                "content": {
                    "stats": [
                        {"value": "LIVE", "label": "URL Trust Gate at app.cyberarmor.ai"},
                        {"value": "<120ms", "label": "live verdicts on real attack pages"},
                        {"value": "15 min", "label": "proof-of-concept installs on a laptop"},
                    ],
                },
                "narration": (
                    "This isn't a deck-stage idea. The U-R-L Trust Gate is live today at app "
                    "dot CyberArmor dot A-I — verdicts in under a hundred and twenty "
                    "milliseconds, blocking real attack pages, with a proof of concept that "
                    "installs on a laptop in fifteen minutes."
                ),
            },
            {
                "id": "comps", "layout": "bar-chart", "variant": "light",
                "content": {
                    "bars": [
                        {"category": "Prompt Security", "segments": [{"label": "Reported exit value ($M)", "value": 250}]},
                        {"category": "Lakera", "segments": [{"label": "Reported exit value ($M)", "value": 300}]},
                        {"category": "Aim Security", "segments": [{"label": "Reported exit value ($M)", "value": 375}]},
                        {"category": "Robust Intelligence", "segments": [{"label": "Reported exit value ($M)", "value": 400}]},
                        {"category": "Protect AI", "segments": [{"label": "Reported exit value ($M)", "value": 600}]},
                    ],
                    "y_label": "Comparable AI-security exits, 2024-2025 ($M)",
                    "note": "Reported by press/media; not officially confirmed. Illustrative context — not a projection.",
                },
                "narration": (
                    "Buyers already pay for this category. Five comparable A-I security exits "
                    "since twenty twenty-four — from two hundred fifty million to roughly "
                    "seven hundred million dollars — by Palo Alto, Cisco, Check Point, Cato, "
                    "and SentinelOne. None of them bought the gate."
                ),
            },
            {
                "id": "blueprint", "layout": "stat-trio", "variant": "dark",
                "content": {
                    "stats": [
                        {"value": "≈$200M", "label": "ARR potential at scale — management scenario: land, expand, anchor"},
                        {"value": "×5", "label": "revenue multiple, public-SaaS precedent"},
                        {"value": "≈$1B", "label": "valuation scenario — an engineered plan, not a claim of current value"},
                    ],
                },
                "narration": (
                    "The blueprint: land with the gate, expand into the runtime platform, "
                    "anchor with compliance — roughly two hundred million dollars of annual "
                    "recurring revenue potential at scale. At a five-times revenue multiple, "
                    "that is the engineered path to a billion-dollar trust layer. A plan — "
                    "not a claim of current value. Today's entry: a fifteen-million-dollar "
                    "cap. Illustrative only."
                ),
            },
            {
                "id": "ask", "layout": "stat-trio", "variant": "dark",
                "content": {
                    "stats": [
                        {"value": "$3M", "label": "SAFE — $15M post-money cap"},
                        {"value": "18 mo", "label": "runway to a clear seed-round metric story"},
                        {"value": "5–10", "label": "paid design partners — the metric this raise proves"},
                    ],
                },
                "narration": (
                    "We're raising three million dollars on a safe, at a fifteen-million "
                    "post-money cap — eighteen months of runway to convert a working product "
                    "into five to ten paid design partners, general availability, and a clear "
                    "seed-round metric story."
                ),
            },
            {
                "id": "cta", "layout": "close", "variant": "dark",
                "content": {
                    "headline": "Book the 15-minute proof-of-concept.",
                    "sub": "pk@cyberarmor.ai · cyberarmor.ai",
                },
                "narration": (
                    "Every A-I in your company reads the internet. Book the fifteen-minute "
                    "proof of concept and watch the gate block live attacks on your own "
                    "laptop. CyberArmor A-I — the trust layer for enterprise A-I."
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
