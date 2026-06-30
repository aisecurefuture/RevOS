"""Master seed: owner user, default pipeline, 5 brands, Hao campaign, and an
optional LinkedIn contact import.

Run it with:  python -m app.seed.seed
Idempotent — safe to run repeatedly.

Optional LinkedIn import: set SEED_LINKEDIN_CSV to the path of your
Connections.csv to import it into the personal brand as CRM contacts (NOT a
mailable marketing list).
"""

from __future__ import annotations

import asyncio
import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.core.security import hash_password
from app.database import AsyncSessionLocal, async_engine
from app.models.brand import Brand
from app.models.user import AdminUser, Role
from app.seed.brands import seed_brands
from app.seed.hao_campaign import seed_hao_campaign
from app.services import crm_service, linkedin_import
from app.services.auth_service import get_user_by_email
from app.services.crud import get_active  # noqa: F401  (ensures models import)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("revos.seed")


async def ensure_owner(db: AsyncSession) -> bool:
    existing = await get_user_by_email(db, settings.owner_email)
    if existing is not None:
        return False
    db.add(AdminUser(
        email=settings.owner_email.lower().strip(),
        hashed_password=hash_password(settings.owner_password),
        full_name=settings.owner_name, role=Role.owner,
    ))
    await db.flush()
    logger.info("Created owner user %s", settings.owner_email)
    return True


async def maybe_import_linkedin(db: AsyncSession) -> int:
    path = os.environ.get("SEED_LINKEDIN_CSV")
    if not path or not os.path.exists(path):
        return 0
    # Import into the personal brand if present, else global.
    personal = (await db.execute(
        select(Brand).where(Brand.slug == "patrick-m-kelly-jr"))).scalar_one_or_none()
    with open(path, encoding="utf-8-sig") as fh:
        rows = linkedin_import.parse_contacts_csv(fh.read())
    result = await linkedin_import.import_contacts(
        db, brand_id=personal.id if personal else None, rows=rows)
    logger.info("LinkedIn import: %s", result)
    return result["created"]


async def seed_all(db: AsyncSession) -> dict:
    owner_created = await ensure_owner(db)
    await crm_service.ensure_default_pipeline(db, None)
    brands_created = await seed_brands(db)
    hao = await seed_hao_campaign(db)
    linkedin_count = await maybe_import_linkedin(db)
    return {
        "owner_created": owner_created,
        "brands_created": brands_created,
        "hao_created": hao.get("created", False),
        "linkedin_contacts_imported": linkedin_count,
    }


async def _run() -> None:
    async with AsyncSessionLocal() as session:
        summary = await seed_all(session)
        await session.commit()
    await async_engine.dispose()
    logger.info("Seed complete: %s", summary)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
