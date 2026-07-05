"""Brand Book — the grounding source of truth for AI generation (Phase 3 M1).

Complements the existing brand context (Brand, BrandVoice, BuyerPersona,
Audience, Offer) with the *substance* and *verifiable knowledge* that grounding
and hallucination control need:

* ``BrandBook`` (1:1 with a brand) — mission, positioning, key messages, and the
  hard guardrails: banned terms, required disclaimers, compliance notes.
* ``BrandClaim`` — approved, verifiable proof points. Generated content's
  factual claims are checked against these; a numeric claim not backed by an
  approved claim is treated as a likely hallucination.
* ``BrandFact`` — freeform knowledge-base entries the AI may ground on.

BrandVoice already holds *how* to say things (tone, style, do/don't); this holds
*what is true* and *what must never be said*.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, TenantModel


class ClaimCategory(StrEnum):
    metric = "metric"                # "10,000+ customers", "99.9% uptime"
    certification = "certification"  # "SOC 2 Type II"
    feature = "feature"              # "one-click export"
    testimonial = "testimonial"
    award = "award"
    partnership = "partnership"
    other = "other"


class BrandBook(TenantModel, table=True):
    """1:1 grounding record for a brand."""

    __tablename__ = "brand_books"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True, unique=True)

    mission: str | None = Field(default=None, sa_type=sa.Text)
    positioning: str | None = Field(default=None, sa_type=sa.Text)     # how we're different
    elevator_pitch: str | None = Field(default=None, sa_type=sa.Text)
    target_summary: str | None = Field(default=None, sa_type=sa.Text)  # one-paragraph ICP
    key_messages: list = Field(default_factory=list, sa_type=JSON)

    # --- Guardrails (the hallucination / safety substrate) ------------------
    # Hard-blocked words/phrases — any generated content containing one is rejected.
    banned_terms: list = Field(default_factory=list, sa_type=JSON)
    # Phrases that must appear in certain content (e.g. legal disclaimers).
    required_disclaimers: list = Field(default_factory=list, sa_type=JSON)
    # Freeform compliance guidance injected into every generation prompt.
    compliance_notes: str | None = Field(default=None, sa_type=sa.Text)
    competitors: list = Field(default_factory=list, sa_type=JSON)

    # Only a published book is used to ground live generation.
    is_published: bool = Field(default=False, index=True)


class BrandClaim(TenantModel, table=True):
    """An approved, verifiable proof point. The anchor for claim verification."""

    __tablename__ = "brand_claims"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    claim: str = Field(max_length=500)
    proof: str | None = Field(default=None, sa_type=sa.Text)  # evidence / source
    category: ClaimCategory = Field(default=ClaimCategory.other, sa_type=sa.String(16))
    approved: bool = Field(default=True, index=True)
    expires_at: datetime | None = Field(default=None)         # time-bound claims
    created_by: uuid.UUID = Field(foreign_key="admin_users.id", index=True)


class BrandFact(TenantModel, table=True):
    """A knowledge-base entry the AI may ground on (Q&A / fact snippet)."""

    __tablename__ = "brand_facts"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    topic: str = Field(max_length=300)
    content: str = Field(sa_type=sa.Text)
    category: str | None = Field(default=None, max_length=100)
    source: str | None = Field(default=None, max_length=500)
    created_by: uuid.UUID = Field(foreign_key="admin_users.id", index=True)
