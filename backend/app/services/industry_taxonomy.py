"""Backend mirror of the industry taxonomy (frontend/src/lib/industries.ts).

The frontend owns the picker UX; the backend needs the slug→category rollup so
rating cohorts can be scoped *within* an industry (exact slug) or *across* one
(the 11 rollup categories), plus follower size tiers — the second cohort axis
that keeps ratings comparing like-with-like.

Keep the slug set in sync with industries.ts. Unknown slugs are allowed (free
text is never gated) but simply don't roll up.
"""

from __future__ import annotations

# slug -> rollup category (the 11 IndustryCategory groups in industries.ts)
INDUSTRY_CATEGORY: dict[str, str] = {
    # trades & home services
    "general_contractor": "trades", "electrician": "trades", "plumber": "trades",
    "carpenter": "trades", "builder": "trades", "hvac_technician": "trades",
    "landscaper": "trades", "roofer": "trades", "handyman": "trades",
    "cleaning_service": "trades",
    # professional services
    "lawyer": "professional", "accountant": "professional", "financial_advisor": "professional",
    "insurance_agent": "professional", "consultant": "professional", "bookkeeper": "professional",
    # healthcare
    "doctor": "healthcare", "dentist": "healthcare", "chiropractor": "healthcare",
    "optometrist": "healthcare", "veterinarian": "healthcare", "therapist": "healthcare",
    "nutritionist": "healthcare", "physical_therapist": "healthcare",
    # real estate & property
    "real_estate_agent": "real_estate", "property_manager": "real_estate",
    "mortgage_broker": "real_estate", "interior_designer": "real_estate",
    # finance & investment
    "banker": "finance", "investor": "finance", "wealth_manager": "finance",
    # creators & artists
    "artist": "creators", "musician": "creators", "painter": "creators", "actor": "creators",
    "author": "creators", "photographer": "creators", "content_creator": "creators",
    "podcaster": "creators", "filmmaker": "creators", "designer": "creators",
    # public figures
    "public_figure": "public", "philanthropist": "public", "speaker_coach": "public",
    "politician": "public",
    # marketing & media
    "marketing_agency": "marketing", "marketing_strategist": "marketing",
    "brand_manager": "marketing", "social_media_manager": "marketing",
    "pr_communications": "marketing",
    # technology
    "software_engineer": "technology", "ai_engineer": "technology", "entrepreneur": "technology",
    "product_manager": "technology", "it_services": "technology",
    # business & retail
    "retail_business": "business", "ecommerce": "business", "restaurant": "business",
    "fitness": "business", "salon_spa": "business", "freelancer": "business",
    "small_business": "business",
}

CATEGORIES: tuple[str, ...] = (
    "trades", "professional", "healthcare", "real_estate", "finance",
    "creators", "public", "marketing", "technology", "business", "other",
)


def rollup(slug: str | None) -> str | None:
    """The rollup category for an industry slug (for cross-industry cohorts)."""
    if not slug:
        return None
    return INDUSTRY_CATEGORY.get(slug.strip().lower())


def is_known(slug: str | None) -> bool:
    return bool(slug) and slug.strip().lower() in INDUSTRY_CATEGORY


# --- Follower size tiers (the second rating-cohort axis) --------------------
# (label, minimum follower count). Highest threshold first for lookup.
SIZE_TIERS: tuple[tuple[str, int], ...] = (
    ("mega", 1_000_000),
    ("macro", 500_000),
    ("mid", 100_000),
    ("micro", 10_000),
    ("nano", 0),
)


def size_tier_for(follower_count: int | None) -> str | None:
    if follower_count is None:
        return None
    for label, floor in SIZE_TIERS:
        if follower_count >= floor:
            return label
    return "nano"
