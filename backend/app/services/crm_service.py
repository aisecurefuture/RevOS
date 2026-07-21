"""CRM service: contacts, companies, deals, pipeline, notes, tasks, scoring."""

from __future__ import annotations

import csv
import io
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.text import clean_text
from app.models.base import utcnow
from app.models.crm import Company, Contact, Deal, Note, PipelineStage, Task
from app.services.crud import list_active

# Default sales pipeline (seeded once per scope).
DEFAULT_STAGES = [
    ("New lead", "new-lead", 0, 10, False, False),
    ("Engaged", "engaged", 1, 20, False, False),
    ("Qualified", "qualified", 2, 35, False, False),
    ("Meeting requested", "meeting-requested", 3, 50, False, False),
    ("Proposal sent", "proposal-sent", 4, 65, False, False),
    ("Negotiation", "negotiation", 5, 80, False, False),
    ("Won", "won", 6, 100, True, False),
    ("Lost", "lost", 7, 0, False, True),
    ("Nurture", "nurture", 8, 15, False, False),
]

_SENIORITY = (
    "chief", "ciso", "cto", "cio", "ceo", "cfo", "founder", "co-founder",
    "president", "vp", "vice president", "head", "director", "partner",
    "owner", "principal", "managing",
)


def score_contact(*, email: str | None, title: str | None, has_company: bool,
                   linkedin: str | None) -> int:
    """Lightweight rule-based lead score (0-45)."""
    score = 0
    if email:
        score += 10
    if title:
        t = title.lower()
        score += 25 if any(k in t for k in _SENIORITY) else 5
    if has_company:
        score += 5
    if linkedin:
        score += 5
    return score


# --- Pipeline ---------------------------------------------------------------
async def ensure_default_pipeline(
    db: AsyncSession, brand_id: uuid.UUID | None = None
) -> list[PipelineStage]:
    result = await db.execute(
        select(PipelineStage).where(
            PipelineStage.brand_id == brand_id, PipelineStage.deleted_at.is_(None)
        ).order_by(PipelineStage.order_index)
    )
    existing = list(result.scalars().all())
    if existing:
        return existing
    stages = [
        PipelineStage(brand_id=brand_id, name=n, slug=s, order_index=o,
                      probability=p, is_won=w, is_lost=lost)
        for (n, s, o, p, w, lost) in DEFAULT_STAGES
    ]
    for stage in stages:
        db.add(stage)
    await db.flush()
    return stages


async def list_pipeline(db: AsyncSession, brand_id: uuid.UUID | None) -> list[PipelineStage]:
    return await list_active(db, PipelineStage, filters=[PipelineStage.brand_id == brand_id],
                             order_by=PipelineStage.order_index)


# --- Companies --------------------------------------------------------------
async def find_or_create_company(
    db: AsyncSession, brand_id: uuid.UUID | None, name: str
) -> Company:
    name = clean_text(name) or name
    result = await db.execute(
        select(Company).where(
            Company.brand_id == brand_id, Company.name == name, Company.deleted_at.is_(None)
        )
    )
    company = result.scalar_one_or_none()
    if company is None:
        company = Company(brand_id=brand_id, name=name)
        db.add(company)
        await db.flush()
        await db.refresh(company)
    return company


# --- Contacts ---------------------------------------------------------------
async def find_contact(
    db: AsyncSession, brand_id: uuid.UUID | None, *, email: str | None, linkedin: str | None
) -> Contact | None:
    conds = [Contact.brand_id == brand_id, Contact.deleted_at.is_(None)]
    if email:
        result = await db.execute(select(Contact).where(*conds, Contact.email == email.lower()))
        found = result.scalar_one_or_none()
        if found:
            return found
    if linkedin:
        result = await db.execute(select(Contact).where(*conds, Contact.linkedin_url == linkedin))
        return result.scalar_one_or_none()
    return None


def normalize_channels(entries: list | None, scalar: str | None) -> tuple[list[dict], str | None]:
    """Clean a list of {value,label,is_primary} channels (email or phone),
    de-dupe, guarantee exactly one primary, and return (list, primary_value).

    If no list is given, synthesize one from the scalar column so legacy rows
    and simple single-value writes stay consistent.
    """
    cleaned: list[dict] = []
    seen: set[str] = set()
    for e in entries or []:
        raw = e if isinstance(e, dict) else e.model_dump()
        value = clean_text(raw.get("value"))
        if not value or value.lower() in seen:
            continue
        seen.add(value.lower())
        cleaned.append({
            "value": value,
            "label": clean_text(raw.get("label")),
            "is_primary": bool(raw.get("is_primary")),
        })
    if not cleaned and scalar:
        cleaned = [{"value": scalar, "label": None, "is_primary": True}]
    if cleaned:
        primaries = [c for c in cleaned if c["is_primary"]]
        if not primaries:
            cleaned[0]["is_primary"] = True
        else:
            for c in primaries[1:]:      # only the first primary stays primary
                c["is_primary"] = False
    primary_value = next((c["value"] for c in cleaned if c["is_primary"]), None)
    return cleaned, primary_value


async def create_contact(db: AsyncSession, data: dict) -> Contact:
    emails, primary_email = normalize_channels(data.pop("emails", None), data.get("email"))
    phones, primary_phone = normalize_channels(data.pop("phones", None), data.get("phone"))
    data["emails"] = emails
    data["phones"] = phones
    if primary_email:
        data["email"] = primary_email
    if primary_phone:
        data["phone"] = primary_phone
    contact = Contact(**data)
    contact.lead_score = score_contact(
        email=contact.email, title=contact.title,
        has_company=contact.company_id is not None, linkedin=contact.linkedin_url,
    )
    db.add(contact)
    await db.flush()
    await db.refresh(contact)
    return contact


async def update_contact(db: AsyncSession, contact: Contact, data: dict) -> Contact:
    """Apply a partial update. Channel lists (emails/phones) are normalized and
    their primary mirrored back into the scalar email/phone columns."""
    if data.get("email"):
        data["email"] = str(data["email"]).lower()

    if "emails" in data:
        emails, primary = normalize_channels(data.pop("emails"), data.get("email") or contact.email)
        contact.emails = emails
        if primary:
            contact.email = primary
    if "phones" in data:
        phones, primary = normalize_channels(data.pop("phones"), data.get("phone") or contact.phone)
        contact.phones = phones
        contact.phone = primary or contact.phone

    for key, value in data.items():
        setattr(contact, key, value)

    contact.lead_score = score_contact(
        email=contact.email, title=contact.title,
        has_company=contact.company_id is not None, linkedin=contact.linkedin_url,
    )
    db.add(contact)
    await db.flush()
    await db.refresh(contact)
    return contact


async def find_or_create_contact(
    db: AsyncSession, *, brand_id: uuid.UUID, email: str,
    first_name: str | None = None, last_name: str | None = None,
    phone: str | None = None, title: str | None = None, source: str | None = None,
    emails: list | None = None, phones: list | None = None,
    notes: str | None = None, address: dict | None = None,
) -> Contact:
    """Return an existing contact for this brand+email (resurrecting a
    soft-deleted one) or create a new one. Fills blanks only — never
    overwrites known-good data with empties."""
    email = email.lower().strip()
    result = await db.execute(
        select(Contact).where(Contact.brand_id == brand_id, Contact.email == email)
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        contact = Contact(brand_id=brand_id, email=email, source=source)
    elif contact.deleted_at is not None:
        contact.deleted_at = None

    contact.first_name = contact.first_name or clean_text(first_name)
    contact.last_name = contact.last_name or clean_text(last_name)
    contact.title = contact.title or clean_text(title)
    contact.notes = contact.notes or clean_text(notes)
    if source and not contact.source:
        contact.source = source

    # Multi-value channels: set only when this contact has none yet.
    email_list, primary_email = normalize_channels(emails, email)
    phone_list, primary_phone = normalize_channels(phones, phone)
    if not contact.emails:
        contact.emails = email_list
        contact.email = primary_email or contact.email
    if not contact.phones and phone_list:
        contact.phones = phone_list
        contact.phone = contact.phone or primary_phone

    # Address: fill blank fields only.
    for field in ("address_line1", "address_line2", "city", "region", "postal_code", "country"):
        if not getattr(contact, field) and (address or {}).get(field):
            setattr(contact, field, clean_text((address or {}).get(field)))

    contact.lead_score = score_contact(
        email=contact.email, title=contact.title,
        has_company=contact.company_id is not None, linkedin=contact.linkedin_url,
    )
    db.add(contact)
    await db.flush()
    await db.refresh(contact)
    return contact


async def list_contacts(
    db: AsyncSession, *, brand_id: uuid.UUID | None = None, source: str | None = None,
    search: str | None = None, limit: int = 50, offset: int = 0,
) -> list[Contact]:
    filters: list = []
    if brand_id:
        filters.append(Contact.brand_id == brand_id)
    if source:
        filters.append(Contact.source == source)
    if search:
        like = f"%{search.lower()}%"
        filters.append(
            (Contact.email.ilike(like)) | (Contact.first_name.ilike(like))
            | (Contact.last_name.ilike(like))
        )
    return await list_active(db, Contact, filters=filters, order_by=Contact.lead_score.desc(),
                             limit=limit, offset=offset)


def contacts_to_csv(contacts: list[Contact]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["first_name", "last_name", "email", "title", "linkedin_url",
                     "source", "lifecycle_stage", "lead_score"])
    for c in contacts:
        writer.writerow([c.first_name or "", c.last_name or "", c.email or "",
                         c.title or "", c.linkedin_url or "", c.source or "",
                         c.lifecycle_stage, c.lead_score])
    return buffer.getvalue()


# --- Notes / tasks ----------------------------------------------------------
async def create_note(db: AsyncSession, data: dict) -> Note:
    note = Note(**data)
    db.add(note)
    await db.flush()
    await db.refresh(note)
    return note


async def list_notes(db: AsyncSession, entity_type: str, entity_id: uuid.UUID) -> list[Note]:
    result = await db.execute(
        select(Note).where(
            Note.entity_type == entity_type, Note.entity_id == entity_id,
            Note.deleted_at.is_(None),
        ).order_by(Note.pinned.desc(), Note.created_at.desc())
    )
    return list(result.scalars().all())


async def create_task(db: AsyncSession, data: dict) -> Task:
    task = Task(**data)
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


async def complete_task(db: AsyncSession, task: Task) -> Task:
    from app.models.crm import TaskStatus
    task.status = TaskStatus.done
    task.completed_at = utcnow()
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


# --- Deals ------------------------------------------------------------------
async def create_deal(db: AsyncSession, data: dict) -> Deal:
    brand_id = data.get("brand_id")
    if not data.get("pipeline_stage_id"):
        stages = await ensure_default_pipeline(db, brand_id)
        data["pipeline_stage_id"] = stages[0].id
    deal = Deal(**data)
    db.add(deal)
    await db.flush()
    await db.refresh(deal)
    return deal
