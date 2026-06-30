"""Reusable content libraries: pillars, hooks, CTAs, hashtags.

Note: this module deliberately does NOT use ``from __future__ import
annotations`` — the dynamic CRUD factory below relies on the ``body:`` parameter
annotation being the real schema class at definition time so FastAPI can detect
the request body.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.audit import write_audit
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.content import CTA, Hashtag, Hook, Pillar
from app.models.user import AdminUser
from app.schemas.content import (
    CTACreate,
    CTAOut,
    HashtagCreate,
    HashtagOut,
    HookCreate,
    HookOut,
    PillarCreate,
    PillarOut,
)
from app.services import content_service

router = APIRouter(prefix="/content-library", tags=["content-library"])


def _crud(path: str, model, create_schema, out_schema, action: str):
    @router.get(f"/{path}", response_model=list[out_schema], name=f"list_{path}")
    async def _list(
        db: DbSession,
        _user: Annotated[AdminUser, Depends(require_authenticated)],
        brand_id: uuid.UUID | None = None,
    ):
        return await content_service.list_library(db, model, brand_id)

    @router.post(f"/{path}", response_model=out_schema, status_code=201, name=f"create_{path}")
    async def _create(
        body: create_schema,
        request: Request,
        db: DbSession,
        user: Annotated[AdminUser, Depends(require_editor)],
        _: None = Depends(verify_csrf),
    ):
        obj = await content_service.create_library_item(db, model, body.model_dump())
        await write_audit(db, action=f"{action}.create", user_id=user.id,
                          entity_type=action, entity_id=str(obj.id), request=request)
        return obj


_crud("pillars", Pillar, PillarCreate, PillarOut, "pillar")
_crud("hooks", Hook, HookCreate, HookOut, "hook")
_crud("ctas", CTA, CTACreate, CTAOut, "cta")
_crud("hashtags", Hashtag, HashtagCreate, HashtagOut, "hashtag")
