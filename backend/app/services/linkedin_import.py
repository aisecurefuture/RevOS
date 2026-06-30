"""LinkedIn (and generic) contact CSV import.

LinkedIn's export has a few preamble lines before the header row; the parser
skips them and maps columns case-insensitively. Imported rows become CRM
**contacts** (``source=linkedin_import``) — they are explicitly NOT added to any
marketing list and are NOT mailable until they separately opt in.
"""

from __future__ import annotations

import csv
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.crm import Company
from app.services import crm_service

_COMPLIANCE_NOTE = (
    "Imported as CRM contacts (source=linkedin_import). NOT added to any "
    "marketing list and NOT mailable until they opt in."
)
# Hard cap on rows parsed from a single upload (DoS guard); larger lists should
# be split or run via a background job.
_MAX_ROWS = 50_000


def parse_contacts_csv(content: str) -> list[dict]:
    """Parse a LinkedIn or generic contacts CSV into normalized dicts."""
    lines = content.splitlines()
    header_idx = 0
    for i, line in enumerate(lines):
        low = line.lower()
        if ("first name" in low and "last name" in low) or low.startswith("email"):
            header_idx = i
            break

    reader = csv.DictReader(lines[header_idx:])
    rows: list[dict] = []
    for raw in reader:
        if len(rows) >= _MAX_ROWS:
            break
        norm = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        email = (norm.get("email address") or norm.get("email") or "").lower() or None
        rows.append({
            "first_name": norm.get("first name") or norm.get("first_name") or None,
            "last_name": norm.get("last name") or norm.get("last_name") or None,
            "email": email,
            "company": norm.get("company") or None,
            "title": norm.get("position") or norm.get("title") or None,
            "linkedin_url": norm.get("url") or norm.get("linkedin_url") or None,
        })
    return rows


async def import_contacts(
    db: AsyncSession,
    *,
    brand_id: uuid.UUID | None,
    rows: list[dict],
    source: str = "linkedin_import",
) -> dict:
    created = updated = skipped = companies_created = 0
    company_cache: dict[str, uuid.UUID] = {}

    for row in rows:
        if not (row["first_name"] or row["last_name"] or row["email"]):
            skipped += 1
            continue

        company_id = None
        if row["company"]:
            key = row["company"].strip().lower()
            if key in company_cache:
                company_id = company_cache[key]
            else:
                existing = (await db.execute(
                    select(Company).where(
                        Company.brand_id == brand_id, Company.name == row["company"],
                        Company.deleted_at.is_(None),
                    )
                )).scalar_one_or_none()
                if existing is None:
                    company = await crm_service.find_or_create_company(db, brand_id, row["company"])
                    companies_created += 1
                    company_id = company.id
                else:
                    company_id = existing.id
                company_cache[key] = company_id

        contact = await crm_service.find_contact(
            db, brand_id, email=row["email"], linkedin=row["linkedin_url"]
        )
        if contact is not None:
            contact.first_name = contact.first_name or row["first_name"]
            contact.last_name = contact.last_name or row["last_name"]
            contact.title = contact.title or row["title"]
            contact.linkedin_url = contact.linkedin_url or row["linkedin_url"]
            contact.company_id = contact.company_id or company_id
            contact.source = contact.source or source
            db.add(contact)
            updated += 1
        else:
            await crm_service.create_contact(db, {
                "brand_id": brand_id, "company_id": company_id,
                "first_name": row["first_name"], "last_name": row["last_name"],
                "email": row["email"], "title": row["title"],
                "linkedin_url": row["linkedin_url"], "source": source,
            })
            created += 1

    await db.flush()
    return {
        "created": created, "updated": updated, "skipped": skipped,
        "companies_created": companies_created, "note": _COMPLIANCE_NOTE,
    }
