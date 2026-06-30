"""Media pipeline: upload, process into per-platform renditions, approve.

The original upload is stored once and never modified; processing produces new
variant files. Variants are approval-gated before they can be used on a post.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response

from app.core.audit import write_audit
from app.core.exceptions import RevOSError
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.media import MediaAsset
from app.models.user import AdminUser
from app.schemas.media import (
    MediaAssetDetailOut,
    MediaAssetOut,
    MediaVariantOut,
    ProcessRequest,
)
from app.services import media_service
from app.services.storage_service import get_storage

router = APIRouter(prefix="/media", tags=["media"])

_MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB


@router.get("", response_model=list[MediaAssetOut])
async def list_media(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
) -> list[MediaAsset]:
    return await media_service.list_assets(db, brand_id)


@router.post("", response_model=MediaAssetOut, status_code=201)
async def upload_media(
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    file: Annotated[UploadFile, File()],
    brand_id: Annotated[uuid.UUID, Form()],
    _: None = Depends(verify_csrf),
) -> MediaAsset:
    data = await file.read()
    if not data:
        raise RevOSError("Empty file.")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise RevOSError("File too large.")
    asset = await media_service.create_asset(
        db, brand_id=brand_id, uploader_id=user.id,
        filename=file.filename or "upload", data=data, mime=file.content_type,
    )
    await write_audit(db, action="media.upload", user_id=user.id,
                      entity_type="media_asset", entity_id=str(asset.id), request=request)
    return asset


@router.get("/{asset_id}", response_model=MediaAssetDetailOut)
async def get_media(
    asset_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> MediaAssetDetailOut:
    asset = await media_service.get_asset_or_404(db, asset_id)
    detail = MediaAssetDetailOut.model_validate(asset)
    detail.variants = [MediaVariantOut.model_validate(v)
                       for v in await media_service.list_variants(db, asset_id)]
    return detail


@router.post("/{asset_id}/process", response_model=list[MediaVariantOut])
async def process_media(
    asset_id: uuid.UUID,
    body: ProcessRequest,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> list[MediaVariantOut]:
    asset = await media_service.get_asset_or_404(db, asset_id)
    variants = await media_service.process_asset(
        db, asset, platforms=body.platforms or None, enhance=body.enhance)
    await write_audit(db, action="media.process", user_id=user.id,
                      entity_type="media_asset", entity_id=str(asset_id),
                      request=request, meta={"variants": len(variants)})
    return [MediaVariantOut.model_validate(v) for v in variants]


@router.post("/variants/{variant_id}/approve", response_model=MediaVariantOut)
async def approve_variant(
    variant_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> MediaVariantOut:
    variant = await media_service.get_variant_or_404(db, variant_id)
    variant = await media_service.approve_variant(db, variant)
    await write_audit(db, action="media.variant_approve", user_id=user.id,
                      entity_type="media_variant", entity_id=str(variant_id), request=request)
    return MediaVariantOut.model_validate(variant)


@router.get("/{asset_id}/original")
async def download_original(
    asset_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> Response:
    asset = await media_service.get_asset_or_404(db, asset_id)
    data = get_storage().read(asset.original_path)
    return Response(content=data, media_type=asset.mime_type or "application/octet-stream")


@router.get("/variants/{variant_id}/file")
async def download_variant(
    variant_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> Response:
    variant = await media_service.get_variant_or_404(db, variant_id)
    data = get_storage().read(variant.path)
    media_type = "video/mp4" if variant.format == "mp4" else "image/jpeg"
    return Response(content=data, media_type=media_type)
