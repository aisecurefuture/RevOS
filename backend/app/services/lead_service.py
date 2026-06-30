"""Lead persistence: find-or-create, tagging, listing, CSV export."""

from __future__ import annotations

import csv
import io
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.text import clean_text
from app.models.lead import ConsentStatus, Lead, LeadTagLink, Tag
from app.services.crud import list_active


async def find_or_create_lead(
    db: AsyncSession,
    *,
    brand_id: uuid.UUID,
    email: str,
    first_name: str | None = None,
    last_name: str | None = None,
    phone: str | None = None,
    company_name: str | None = None,
    source: str | None = None,
) -> tuple[Lead, bool]:
    """Return (lead, created). Reuses an existing row for the same brand+email
    (un-deleting a soft-deleted one) so the unique constraint never trips."""
    email = email.lower().strip()
    result = await db.execute(
        select(Lead).where(Lead.brand_id == brand_id, Lead.email == email)
    )
    lead = result.scalar_one_or_none()
    created = False
    if lead is None:
        lead = Lead(brand_id=brand_id, email=email, source=source)
        created = True
    elif lead.deleted_at is not None:
        lead.deleted_at = None  # resurrect rather than violate uniqueness

    # Fill blanks only — never overwrite known good data with empties.
    lead.first_name = lead.first_name or clean_text(first_name)
    lead.last_name = lead.last_name or clean_text(last_name)
    lead.phone = lead.phone or clean_text(phone)
    lead.company_name = lead.company_name or clean_text(company_name)
    if source and not lead.source:
        lead.source = source

    db.add(lead)
    await db.flush()
    await db.refresh(lead)
    return lead, created


async def get_or_create_tag(db: AsyncSession, brand_id: uuid.UUID, name: str) -> Tag:
    name = clean_text(name) or name
    result = await db.execute(
        select(Tag).where(Tag.brand_id == brand_id, Tag.name == name)
    )
    tag = result.scalar_one_or_none()
    if tag is None:
        tag = Tag(brand_id=brand_id, name=name)
        db.add(tag)
        await db.flush()
        await db.refresh(tag)
    return tag


async def apply_tags(
    db: AsyncSession, lead: Lead, tag_names: list[str], brand_id: uuid.UUID
) -> None:
    for name in tag_names:
        if not name:
            continue
        tag = await get_or_create_tag(db, brand_id, name)
        existing = await db.execute(
            select(LeadTagLink).where(
                LeadTagLink.lead_id == lead.id, LeadTagLink.tag_id == tag.id
            )
        )
        if existing.scalar_one_or_none() is None:
            db.add(LeadTagLink(lead_id=lead.id, tag_id=tag.id))
    await db.flush()


async def list_lead_tags(db: AsyncSession, lead_id: uuid.UUID) -> list[Tag]:
    result = await db.execute(
        select(Tag).join(LeadTagLink, LeadTagLink.tag_id == Tag.id).where(
            LeadTagLink.lead_id == lead_id
        )
    )
    return list(result.scalars().all())


async def list_leads(
    db: AsyncSession,
    *,
    brand_id: uuid.UUID | None = None,
    consent_status: ConsentStatus | None = None,
    source: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Lead]:
    filters: list = []
    if brand_id:
        filters.append(Lead.brand_id == brand_id)
    if consent_status:
        filters.append(Lead.consent_status == consent_status)
    if source:
        filters.append(Lead.source == source)
    if search:
        like = f"%{search.lower()}%"
        filters.append(Lead.email.ilike(like))
    return await list_active(db, Lead, filters=filters, limit=limit, offset=offset)


def leads_to_csv(leads: list[Lead]) -> str:
    """Serialize leads to a CSV string for export."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["email", "first_name", "last_name", "company", "phone",
         "consent_status", "source", "lead_score", "created_at"]
    )
    for lead in leads:
        writer.writerow([
            lead.email, lead.first_name or "", lead.last_name or "",
            lead.company_name or "", lead.phone or "", lead.consent_status,
            lead.source or "", lead.lead_score, lead.created_at.isoformat(),
        ])
    return buffer.getvalue()
