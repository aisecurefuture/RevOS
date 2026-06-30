"""Notes and follow-up tasks (attachable to any CRM entity)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import write_audit
from app.core.text import clean_text
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.crm import Note, Task, TaskStatus
from app.models.user import AdminUser
from app.schemas.crm import NoteCreate, NoteOut, TaskCreate, TaskOut, TaskUpdate
from app.services import crm_service
from app.services.crud import get_active, list_active

notes_router = APIRouter(prefix="/notes", tags=["notes"])
tasks_router = APIRouter(prefix="/tasks", tags=["tasks"])


# --- Notes ------------------------------------------------------------------
@notes_router.get("", response_model=list[NoteOut])
async def list_notes(
    entity_type: str,
    entity_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> list[Note]:
    return await crm_service.list_notes(db, entity_type, entity_id)


@notes_router.post("", response_model=NoteOut, status_code=201)
async def create_note(
    body: NoteCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Note:
    data = body.model_dump()
    data["body"] = clean_text(data["body"]) or data["body"]
    data["author_user_id"] = user.id
    note = await crm_service.create_note(db, data)
    await write_audit(db, action="note.create", user_id=user.id,
                      entity_type="note", entity_id=str(note.id), request=request)
    return note


# --- Tasks ------------------------------------------------------------------
@tasks_router.get("", response_model=list[TaskOut])
async def list_tasks(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
    status: TaskStatus | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Task]:
    filters: list = []
    if brand_id:
        filters.append(Task.brand_id == brand_id)
    if status:
        filters.append(Task.status == status)
    return await list_active(db, Task, filters=filters, order_by=Task.due_at,
                             limit=limit, offset=offset)


@tasks_router.post("", response_model=TaskOut, status_code=201)
async def create_task(
    body: TaskCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Task:
    data = body.model_dump()
    data["title"] = clean_text(data["title"]) or data["title"]
    if not data.get("assignee_user_id"):
        data["assignee_user_id"] = user.id
    task = await crm_service.create_task(db, data)
    await write_audit(db, action="task.create", user_id=user.id,
                      entity_type="task", entity_id=str(task.id), request=request)
    return task


@tasks_router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID,
    body: TaskUpdate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Task:
    task = await get_active(db, Task, task_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(task, key, value)
    db.add(task)
    await db.flush()
    await db.refresh(task)
    await write_audit(db, action="task.update", user_id=user.id,
                      entity_type="task", entity_id=str(task_id), request=request)
    return task


@tasks_router.post("/{task_id}/complete", response_model=TaskOut)
async def complete_task(
    task_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Task:
    task = await get_active(db, Task, task_id)
    return await crm_service.complete_task(db, task)
