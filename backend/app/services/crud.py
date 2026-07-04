"""Generic async CRUD helpers shared across resource services.

Centralizes soft-delete filtering, 404 handling, pagination bounds, and
per-scope unique-slug generation so resource services stay small.
"""

from __future__ import annotations

from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, select

from app.core.exceptions import NotFoundError
from app.core.tenancy import get_active_account, is_tenant_scoped, scope_stmt
from app.models.base import utcnow

T = TypeVar("T", bound=SQLModel)

MAX_PAGE_SIZE = 200


async def get_active(db: AsyncSession, model: type[T], obj_id) -> T:
    """Fetch a non-soft-deleted row or raise NotFoundError.

    When an active account is set and the model is tenant-scoped, the fetch is
    filtered to that account (joining through Brand) — so a cross-tenant id
    resolves to a 404, not another tenant's row.
    """
    account_id = get_active_account()
    if account_id is not None and is_tenant_scoped(model):
        stmt = select(model).where(
            model.id == obj_id,  # type: ignore[attr-defined]
            model.deleted_at.is_(None),  # type: ignore[attr-defined]
        )
        stmt = scope_stmt(stmt, model, account_id)
        obj = (await db.execute(stmt)).scalars().first()
        if obj is None:
            raise NotFoundError(f"{model.__name__} not found.")
        return obj
    obj = await db.get(model, obj_id)
    if obj is None or getattr(obj, "deleted_at", None) is not None:
        raise NotFoundError(f"{model.__name__} not found.")
    return obj


async def list_active(
    db: AsyncSession,
    model: type[T],
    *,
    filters: list | None = None,
    order_by=None,
    limit: int = 50,
    offset: int = 0,
) -> list[T]:
    stmt = select(model).where(model.deleted_at.is_(None))  # type: ignore[attr-defined]
    account_id = get_active_account()
    if account_id is not None and is_tenant_scoped(model):
        stmt = scope_stmt(stmt, model, account_id)
    for cond in filters or []:
        stmt = stmt.where(cond)
    stmt = stmt.order_by(order_by if order_by is not None else model.created_at.desc())  # type: ignore[attr-defined]
    stmt = stmt.limit(max(1, min(limit, MAX_PAGE_SIZE))).offset(max(0, offset))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def soft_delete(db: AsyncSession, obj: SQLModel) -> None:
    obj.deleted_at = utcnow()  # type: ignore[attr-defined]
    db.add(obj)
    await db.flush()


async def unique_slug(
    db: AsyncSession, model: type[T], base: str, *, brand_id=None
) -> str:
    """Return a slug unique within its scope (per-brand if the model is scoped)."""
    slug = base
    suffix = 2
    scoped = brand_id is not None and hasattr(model, "brand_id")
    while True:
        conds = [model.slug == slug, model.deleted_at.is_(None)]  # type: ignore[attr-defined]
        if scoped:
            conds.append(model.brand_id == brand_id)  # type: ignore[attr-defined]
        result = await db.execute(select(model).where(*conds).limit(1))
        if result.scalar_one_or_none() is None:
            return slug
        slug = f"{base}-{suffix}"
        suffix += 1
