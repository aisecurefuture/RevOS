"""Media processing: probe, store original (immutable), render per-platform
renditions with Pillow (images) / ffmpeg (video), optional enhancement.

The original upload is written once and never modified — every transform writes
a brand-new variant file.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import uuid
from io import BytesIO

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RevOSError
from app.models.content import ContentState
from app.models.media import MediaAsset, MediaKind, MediaStatus, MediaVariant
from app.services.crud import get_active, list_active
from app.services.storage_service import get_storage

logger = logging.getLogger("revos.media")

# Target renditions per platform: (purpose, width, height, aspect).
IMAGE_SPECS: dict[str, list[tuple]] = {
    "instagram": [("feed_square", 1080, 1080, "1:1"), ("feed_portrait", 1080, 1350, "4:5"),
                  ("story", 1080, 1920, "9:16")],
    "facebook": [("feed", 1200, 630, "1.91:1"), ("story", 1080, 1920, "9:16")],
    "twitter": [("feed", 1600, 900, "16:9")],
    "linkedin": [("feed", 1200, 627, "1.91:1")],
    "youtube": [("thumbnail", 1280, 720, "16:9")],
    "tiktok": [("cover", 1080, 1920, "9:16")],
}
VIDEO_SPECS: dict[str, list[tuple]] = {
    "tiktok": [("reel", 1080, 1920, "9:16")],
    "instagram": [("reel", 1080, 1920, "9:16"), ("feed", 1080, 1080, "1:1")],
    "youtube": [("short", 1080, 1920, "9:16"), ("landscape", 1920, 1080, "16:9")],
    "facebook": [("reel", 1080, 1920, "9:16")],
    "twitter": [("feed", 1280, 720, "16:9")],
}

_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}
# Cap video processing to bound CPU/time (long videos belong in a background job).
_MAX_VIDEO_SECONDS = 600.0


def _kind_for(mime: str | None, filename: str) -> MediaKind:
    if mime and mime.startswith("video/"):
        return MediaKind.video
    if mime in _IMAGE_MIME or filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
        return MediaKind.image
    if filename.lower().endswith((".mp4", ".mov", ".webm", ".m4v")):
        return MediaKind.video
    return MediaKind.image


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


# --- Create / store original ------------------------------------------------
async def create_asset(
    db: AsyncSession, *, brand_id: uuid.UUID, uploader_id: uuid.UUID | None,
    filename: str, data: bytes, mime: str | None,
) -> MediaAsset:
    kind = _kind_for(mime, filename)
    checksum = hashlib.sha256(data).hexdigest()
    asset = MediaAsset(
        brand_id=brand_id, uploader_user_id=uploader_id, kind=kind,
        original_filename=filename, original_path="", mime_type=mime,
        size_bytes=len(data), checksum=checksum, status=MediaStatus.uploaded,
    )
    db.add(asset)
    await db.flush()

    storage = get_storage()
    key = f"media/{asset.id}/original/{filename}"
    storage.save(key, data)
    asset.original_path = key

    if kind == MediaKind.image:
        try:
            from PIL import Image
            with Image.open(BytesIO(data)) as img:
                asset.width, asset.height = img.size
        except Exception:  # noqa: BLE001 — bad image still stored, dims unknown
            logger.debug("Image dimension probe failed for %s", filename)
    elif kind == MediaKind.video and ffmpeg_available():
        _probe_video(asset, data)

    db.add(asset)
    await db.flush()
    await db.refresh(asset)
    return asset


def _probe_video(asset: MediaAsset, data: bytes) -> None:
    import json
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
        tmp.write(data)
        tmp.flush()
        try:
            out = subprocess.run(  # noqa: S603 — fixed args, trusted binary
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams",  # noqa: S607
                 "-show_format", tmp.name],
                capture_output=True, text=True, timeout=30, check=False,
            )
            info = json.loads(out.stdout or "{}")
            stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
            asset.width = stream.get("width")
            asset.height = stream.get("height")
            asset.duration_seconds = float(info.get("format", {}).get("duration", 0)) or None
        except Exception:  # noqa: BLE001
            logger.debug("Video probe failed for asset %s", asset.id)


# --- Rendering --------------------------------------------------------------
def _render_image(data: bytes, w: int, h: int, *, enhance: bool) -> bytes:
    from PIL import Image, ImageEnhance, ImageOps

    with Image.open(BytesIO(data)) as img:
        img = img.convert("RGB")
        # Cover-fit: scale to fill then center-crop to the exact target.
        fitted = ImageOps.fit(img, (w, h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        if enhance:
            fitted = ImageOps.autocontrast(fitted)
            fitted = ImageEnhance.Sharpness(fitted).enhance(1.2)
        buf = BytesIO()
        fitted.save(buf, "JPEG", quality=88, optimize=True)
        return buf.getvalue()


def _render_video(src_key: str, w: int, h: int) -> bytes | None:
    """Transcode + crop a video to WxH via ffmpeg. Returns None if unavailable."""
    if not ffmpeg_available():
        return None
    import tempfile

    storage = get_storage()
    data = storage.read(src_key)
    with tempfile.NamedTemporaryFile(suffix=".mp4") as src, \
            tempfile.NamedTemporaryFile(suffix=".mp4") as dst:
        src.write(data)
        src.flush()
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
              f"crop={w}:{h}")
        result = subprocess.run(  # noqa: S603
            ["ffmpeg", "-y", "-i", src.name, "-vf", vf, "-c:a", "copy",  # noqa: S607
             "-movflags", "+faststart", dst.name],
            capture_output=True, timeout=300, check=False,
        )
        if result.returncode != 0:
            return None
        return open(dst.name, "rb").read()  # noqa: SIM115


# --- Process ----------------------------------------------------------------
async def process_asset(
    db: AsyncSession, asset: MediaAsset, *, platforms: list[str] | None, enhance: bool,
) -> list[MediaVariant]:
    # Reject over-long video before spending CPU on transcoding.
    if (asset.kind == MediaKind.video and asset.duration_seconds
            and asset.duration_seconds > _MAX_VIDEO_SECONDS):
        asset.status = MediaStatus.failed
        asset.meta = {**asset.meta, "error": f"video exceeds {_MAX_VIDEO_SECONDS:.0f}s cap"}
        db.add(asset)
        await db.flush()
        raise RevOSError("Video too long to process here; use a shorter clip.")

    asset.status = MediaStatus.processing
    db.add(asset)
    await db.flush()

    storage = get_storage()
    original = storage.read(asset.original_path)
    specs = IMAGE_SPECS if asset.kind == MediaKind.image else VIDEO_SPECS
    targets = platforms or list(specs.keys())
    variants: list[MediaVariant] = []

    try:
        for platform in targets:
            for purpose, w, h, aspect in specs.get(platform, []):
                if asset.kind == MediaKind.image:
                    rendered = _render_image(original, w, h, enhance=enhance)
                    fmt = "jpg"
                else:
                    rendered = _render_video(asset.original_path, w, h)
                    fmt = "mp4"
                    if rendered is None:
                        continue  # ffmpeg unavailable — skip gracefully
                key = f"media/{asset.id}/variants/{platform}_{purpose}.{fmt}"
                storage.save(key, rendered)
                variant = MediaVariant(
                    media_asset_id=asset.id, platform=platform, purpose=purpose,
                    aspect_ratio=aspect, path=key, width=w, height=h, format=fmt,
                    size_bytes=len(rendered), is_ai_enhanced=False,
                    enhancement={"deterministic": enhance}, state=ContentState.draft,
                )
                db.add(variant)
                variants.append(variant)
        asset.status = MediaStatus.ready
    except Exception as exc:  # noqa: BLE001
        asset.status = MediaStatus.failed
        asset.meta = {**asset.meta, "error": str(exc)[:300]}

    db.add(asset)
    await db.flush()
    for v in variants:
        await db.refresh(v)
    return variants


# --- Queries / approval -----------------------------------------------------
async def get_asset_or_404(db: AsyncSession, asset_id: uuid.UUID) -> MediaAsset:
    return await get_active(db, MediaAsset, asset_id)


async def list_assets(db: AsyncSession, brand_id: uuid.UUID | None) -> list[MediaAsset]:
    filters = [MediaAsset.brand_id == brand_id] if brand_id else []
    return await list_active(db, MediaAsset, filters=filters)


async def list_variants(db: AsyncSession, asset_id: uuid.UUID) -> list[MediaVariant]:
    return await list_active(db, MediaVariant,
                             filters=[MediaVariant.media_asset_id == asset_id])


async def get_variant_or_404(db: AsyncSession, variant_id: uuid.UUID) -> MediaVariant:
    return await get_active(db, MediaVariant, variant_id)


async def approve_variant(db: AsyncSession, variant: MediaVariant) -> MediaVariant:
    if variant.state not in (ContentState.draft, ContentState.needs_review):
        raise RevOSError("Variant is not in a reviewable state.")
    variant.state = ContentState.approved
    db.add(variant)
    await db.flush()
    await db.refresh(variant)
    return variant
