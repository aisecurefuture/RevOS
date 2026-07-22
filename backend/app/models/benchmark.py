"""Third-party industry benchmarks (Phase 6 — BM).

RevOS's own cohort benchmarks (``insights_service._creator_cohort_benchmarks``,
``public_profile_service._reputation_percentile``) compare a creator against
*RevOS's own* population — thin or empty for a new marketplace. This table is
the fallback: admin-curated figures read off published third-party reports
(Rival IQ/Quid, Socialinsider), refreshed a few times a year, never a live
per-request API call ("low-cost" per the roadmap).

Platform-wide reference data, not a tenant's own data — plain ``BaseModel``,
writable only by a platform admin.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import BaseModel


class IndustryBenchmark(BaseModel, table=True):
    __tablename__ = "industry_benchmarks"

    # One of the 11 rollup categories in industry_taxonomy.CATEGORIES — matches
    # how published reports segment ("Real Estate", "Beauty", ...), unlike
    # RevOS's ~55 fine-grained industry slugs.
    industry_category: str = Field(index=True, max_length=40)
    # The verbatim industry name as stated in the source report (e.g.
    # "Veterinary Services"), independent of industry_category. Rollup into
    # one of the 11 CATEGORIES is lossy by design (reports use finer-grained
    # segments than our cohort buckets do) — this column is what keeps the
    # real industry from disappearing when a row rolls up to "other".
    industry_label: str | None = Field(default=None, max_length=120)
    # A SocialPlatform value, or the sentinel "all" for a cross-platform
    # figure. NOT nullable: Postgres treats every NULL as distinct in a unique
    # index, which would silently defeat uq_benchmark_figure for "all" rows.
    platform: str = Field(default="all", index=True, max_length=20)
    # "engagement_rate" to start; free-form so a new metric doesn't need a
    # migration.
    metric: str = Field(default="engagement_rate", index=True, max_length=40)
    value: float = Field()

    source: str = Field(max_length=200)              # e.g. "Quid 2026 Social Media Industry Benchmark Report"
    source_url: str | None = Field(default=None, max_length=500)
    period_label: str = Field(max_length=40)          # e.g. "2026 Annual"

    updated_by_user_id: uuid.UUID = Field(foreign_key="admin_users.id")

    __table_args__ = (
        # Re-curating the SAME report doesn't duplicate; a new period_label
        # (a later report) adds a new row, preserving history.
        sa.UniqueConstraint("industry_category", "platform", "metric", "period_label",
                            name="uq_benchmark_figure"),
    )
