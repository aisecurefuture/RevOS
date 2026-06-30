"""Seed data tests (Module 16)."""

from __future__ import annotations

import pytest
from app.models.brand import Brand
from app.models.sequence import Sequence
from app.models.user import AdminUser
from sqlmodel import select


@pytest.mark.asyncio
async def test_seed_is_complete_and_idempotent(async_session_factory):
    from app.seed.seed import seed_all

    async with async_session_factory() as s:
        summary = await seed_all(s)
        await s.commit()

    assert summary["owner_created"] is True
    assert summary["brands_created"] == 5
    assert summary["hao_created"] is True

    async with async_session_factory() as s:
        brands = (await s.execute(select(Brand))).scalars().all()
        assert len(brands) == 6  # 5 default + Hao influencer
        slugs = {b.slug for b in brands}
        assert {"cyberarmor", "ai-secure-future", "hao-jhhfit"} <= slugs

        # CyberArmor + book get starter sequences.
        seqs = (await s.execute(select(Sequence))).scalars().all()
        assert len(seqs) == 2

        owners = (await s.execute(
            select(AdminUser).where(AdminUser.role == "owner"))).scalars().all()
        assert len(owners) == 1

        # Second run creates nothing new.
        summary2 = await seed_all(s)
        await s.commit()
        assert summary2["brands_created"] == 0
        assert summary2["owner_created"] is False
