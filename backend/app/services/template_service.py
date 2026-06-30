"""Email template rendering and CRUD.

Templates may be authored by admins, so rendering uses a **sandboxed** Jinja2
environment (blocks attribute-access escapes / SSTI) with autoescaping on
(blocks XSS in the rendered HTML). Merge variables are passed as a flat context.
"""

from __future__ import annotations

import uuid

from jinja2 import select_autoescape
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.text import clean_text, slugify
from app.models.email import EmailTemplate
from app.services.crud import get_active, list_active, unique_slug

_env = SandboxedEnvironment(
    autoescape=select_autoescape(default=True, default_for_string=True),
)


def render_string(template: str | None, context: dict) -> str:
    if not template:
        return ""
    return _env.from_string(template).render(**context)


async def render_db_template(
    db: AsyncSession, *, brand_id: uuid.UUID | None, slug: str, context: dict
) -> tuple[str, str, str | None]:
    """Render (subject, html, text) for the template matching slug. Prefers a
    brand-scoped template, falling back to a global one."""
    result = await db.execute(
        select(EmailTemplate).where(
            EmailTemplate.slug == slug,
            EmailTemplate.is_active.is_(True),
            EmailTemplate.deleted_at.is_(None),
        ).order_by(EmailTemplate.brand_id.is_(None))  # brand-scoped first
    )
    template = result.scalars().first()
    if template is None:
        raise KeyError(f"No active template '{slug}'")
    return (
        render_string(template.subject, context),
        render_string(template.html_body, context),
        render_string(template.text_body, context) if template.text_body else None,
    )


# --- CRUD -------------------------------------------------------------------
async def list_templates(
    db: AsyncSession, *, brand_id: uuid.UUID | None = None, limit: int = 50, offset: int = 0
) -> list[EmailTemplate]:
    filters = [EmailTemplate.brand_id == brand_id] if brand_id else []
    return await list_active(db, EmailTemplate, filters=filters, limit=limit, offset=offset)


async def get_template_or_404(db: AsyncSession, template_id: uuid.UUID) -> EmailTemplate:
    return await get_active(db, EmailTemplate, template_id)


async def create_template(db: AsyncSession, data: dict) -> EmailTemplate:
    base = slugify(data.get("slug") or data["name"])
    slug = await unique_slug(db, EmailTemplate, base, brand_id=data.get("brand_id"))
    template = EmailTemplate(
        brand_id=data.get("brand_id"),
        name=clean_text(data["name"]) or data["name"],
        slug=slug,
        category=data.get("category", "campaign"),
        subject=data["subject"],
        preheader=clean_text(data.get("preheader")),
        html_body=data["html_body"],
        text_body=data.get("text_body"),
        variables=data.get("variables", []),
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template


async def update_template(db: AsyncSession, template: EmailTemplate, data: dict) -> EmailTemplate:
    for key in ("name", "subject", "preheader", "html_body", "text_body", "category",
                "variables", "is_active"):
        if key in data and data[key] is not None:
            setattr(template, key, data[key])
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template
