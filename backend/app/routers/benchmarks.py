"""Third-party industry benchmarks — admin curation (BM1). Platform-admin
only: this is shared reference data affecting every tenant's dashboards and
public pages, not a tenant's own data."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import write_audit
from app.core.exceptions import RevOSError
from app.deps import DbSession, require_platform_admin, verify_csrf
from app.models.benchmark import IndustryBenchmark
from app.models.user import AdminUser
from app.schemas.benchmark import IndustryBenchmarkCreate, IndustryBenchmarkOut
from app.schemas.common import Message
from app.services import benchmark_service

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


@router.get("", response_model=list[IndustryBenchmarkOut])
async def list_benchmarks(
    db: DbSession,
    _admin: Annotated[AdminUser, Depends(require_platform_admin)],
    industry_category: str | None = Query(default=None),
) -> list[IndustryBenchmark]:
    return await benchmark_service.list_all(db, industry_category=industry_category)


@router.post("", response_model=IndustryBenchmarkOut, status_code=201)
async def create_benchmark(
    body: IndustryBenchmarkCreate,
    request: Request,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_platform_admin)],
    _: None = Depends(verify_csrf),
) -> IndustryBenchmark:
    row = await benchmark_service.create(db, body.model_dump(), updated_by_user_id=admin.id)
    await write_audit(db, action="benchmark.create", user_id=admin.id,
                      entity_type="industry_benchmark", entity_id=str(row.id), request=request)
    return row


@router.delete("/{benchmark_id}", response_model=Message)
async def delete_benchmark(
    benchmark_id: uuid.UUID,
    request: Request,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_platform_admin)],
    _: None = Depends(verify_csrf),
) -> Message:
    row = await db.get(IndustryBenchmark, benchmark_id)
    if row is None or row.deleted_at is not None:
        raise RevOSError("Benchmark not found.", code="not_found", status_code=404)
    await benchmark_service.delete(db, row)
    await write_audit(db, action="benchmark.delete", user_id=admin.id,
                      entity_type="industry_benchmark", entity_id=str(benchmark_id), request=request)
    return Message(status="deleted")
