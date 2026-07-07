"""Persona identity service (Phase 3 M2) — likeness, voice, consent.

Owns identity + media + consent only. No avatar/voice model training happens
here — M3's GPU inference service reads a ``ready`` identity's media and fills
in ``voice_model_ref`` / ``avatar_model_ref`` once trained.

Status is derived, not set directly by the API: it always reflects the actual
state of media + consent, so it can never drift out of sync with reality.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, RevOSError
from app.models.base import utcnow
from app.models.persona_identity import PersonaConsent, PersonaIdentity, PersonaIdentityStatus
from app.models.user import AdminUser
from app.services.storage_service import get_storage

logger = logging.getLogger("revos.persona_identity")

CURRENT_POLICY_VERSION = "2026-07-05"

_MAX_VIDEO_BYTES = 500 * 1024 * 1024   # 500 MB training video
_MAX_AUDIO_BYTES = 50 * 1024 * 1024    # 50 MB voice sample
_MAX_IMAGE_BYTES = 20 * 1024 * 1024
_MAX_REFERENCE_IMAGES = 10


def _normalize_voice_sample(data: bytes) -> bytes:
    """Transcode the uploaded clip to clean mono 24kHz PCM WAV via ffmpeg.

    XTTS-v2 is sensitive to compressed/VBR containers (e.g. a phone-recorded
    .m4a) — a bad sample-rate/duration read during decoding can corrupt both
    the pitch/speed and the cloned voice identity of the output. Falls back to
    the original bytes if ffmpeg is unavailable or the conversion fails —
    voice cloning is best-effort, so this shouldn't hard-block an upload.
    """
    if not shutil.which("ffmpeg"):
        return data
    with tempfile.NamedTemporaryFile(suffix=".src") as src, \
            tempfile.NamedTemporaryFile(suffix=".wav") as dst:
        src.write(data)
        src.flush()
        result = subprocess.run(  # noqa: S603
            ["ffmpeg", "-y", "-i", src.name, "-ac", "1", "-ar", "24000",  # noqa: S607
             "-sample_fmt", "s16", dst.name],
            capture_output=True, timeout=60, check=False,
        )
        if result.returncode != 0:
            logger.warning(
                "Voice sample normalization failed, storing the original upload as-is: %s",
                result.stderr.decode(errors="replace")[-500:],
            )
            return data
        return Path(dst.name).read_bytes()


_MIN_RECOMMENDED_VOICE_SECONDS = 60.0


def _probe_duration_seconds(data: bytes) -> float | None:
    import json

    if not shutil.which("ffprobe"):
        return None
    with tempfile.NamedTemporaryFile(suffix=".audio") as tmp:
        tmp.write(data)
        tmp.flush()
        result = subprocess.run(  # noqa: S603
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", tmp.name],  # noqa: S607
            capture_output=True, text=True, timeout=30, check=False,
        )
        try:
            info = json.loads(result.stdout or "{}")
            return float(info["format"]["duration"])
        except (KeyError, ValueError, TypeError):
            return None


def _has_media(identity: PersonaIdentity) -> bool:
    return bool(
        identity.training_video_path or identity.voice_sample_path or identity.reference_image_paths
    )


async def _active_consent(db: AsyncSession, identity_id: uuid.UUID) -> PersonaConsent | None:
    result = await db.execute(
        select(PersonaConsent).where(
            PersonaConsent.persona_identity_id == identity_id,
            PersonaConsent.is_active.is_(True),
            PersonaConsent.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def _recompute_status(db: AsyncSession, identity: PersonaIdentity) -> None:
    if identity.status == PersonaIdentityStatus.revoked:
        return  # terminal — a new identity must be created to re-consent
    consent = await _active_consent(db, identity.id)
    if consent is not None and _has_media(identity):
        identity.status = PersonaIdentityStatus.ready
    elif _has_media(identity):
        identity.status = PersonaIdentityStatus.pending_consent
    else:
        identity.status = PersonaIdentityStatus.draft
    db.add(identity)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def get_identity(db: AsyncSession, identity_id: uuid.UUID, account_id: uuid.UUID) -> PersonaIdentity:
    result = await db.execute(
        select(PersonaIdentity).where(
            PersonaIdentity.id == identity_id,
            PersonaIdentity.account_id == account_id,
            PersonaIdentity.deleted_at.is_(None),
        )
    )
    identity = result.scalar_one_or_none()
    if identity is None:
        raise NotFoundError("Persona identity not found.")
    return identity


async def list_identities(db: AsyncSession, account_id: uuid.UUID, brand_id: uuid.UUID | None = None) -> list[PersonaIdentity]:
    filters = [PersonaIdentity.account_id == account_id, PersonaIdentity.deleted_at.is_(None)]
    if brand_id is not None:
        filters.append(PersonaIdentity.brand_id == brand_id)
    result = await db.execute(
        select(PersonaIdentity).where(*filters).order_by(PersonaIdentity.created_at.desc())
    )
    return list(result.scalars().all())


async def create_identity(db: AsyncSession, account_id: uuid.UUID, user: AdminUser, data: dict) -> PersonaIdentity:
    identity = PersonaIdentity(account_id=account_id, created_by=user.id, **data)
    db.add(identity)
    await db.flush()
    await db.refresh(identity)
    return identity


async def update_identity(db: AsyncSession, identity_id: uuid.UUID, account_id: uuid.UUID, data: dict) -> PersonaIdentity:
    identity = await get_identity(db, identity_id, account_id)
    if identity.status == PersonaIdentityStatus.revoked:
        raise ConflictError("This identity's consent was revoked and it can no longer be edited.")
    for key, value in data.items():
        setattr(identity, key, value)
    db.add(identity)
    await db.flush()
    await db.refresh(identity)
    return identity


async def delete_identity(db: AsyncSession, identity_id: uuid.UUID, account_id: uuid.UUID) -> None:
    identity = await get_identity(db, identity_id, account_id)
    identity.deleted_at = utcnow()
    db.add(identity)
    await db.flush()


# ---------------------------------------------------------------------------
# Media uploads
# ---------------------------------------------------------------------------

async def upload_training_video(
    db: AsyncSession, identity_id: uuid.UUID, account_id: uuid.UUID,
    filename: str, data: bytes, mime: str | None,
) -> PersonaIdentity:
    identity = await get_identity(db, identity_id, account_id)
    if identity.status == PersonaIdentityStatus.revoked:
        raise ConflictError("This identity's consent was revoked.")
    if not data:
        raise RevOSError("Empty file.", code="empty_file", status_code=400)
    if len(data) > _MAX_VIDEO_BYTES:
        raise RevOSError("Training video is too large (max 500MB).", code="file_too_large", status_code=400)
    if mime and not mime.startswith("video/"):
        raise RevOSError("Expected a video file.", code="invalid_mime", status_code=400)

    storage = get_storage()
    key = f"personas/{identity.id}/video/{filename}"
    storage.save(key, data)
    identity.training_video_path = key
    await _recompute_status(db, identity)
    await db.flush()
    await db.refresh(identity)
    return identity


async def upload_voice_sample(
    db: AsyncSession, identity_id: uuid.UUID, account_id: uuid.UUID,
    filename: str, data: bytes, mime: str | None,
) -> tuple[PersonaIdentity, str | None]:
    identity = await get_identity(db, identity_id, account_id)
    if identity.status == PersonaIdentityStatus.revoked:
        raise ConflictError("This identity's consent was revoked.")
    if not data:
        raise RevOSError("Empty file.", code="empty_file", status_code=400)
    if len(data) > _MAX_AUDIO_BYTES:
        raise RevOSError("Voice sample is too large (max 50MB).", code="file_too_large", status_code=400)
    if mime and not mime.startswith("audio/"):
        raise RevOSError("Expected an audio file.", code="invalid_mime", status_code=400)

    storage = get_storage()
    data = _normalize_voice_sample(data)
    key = f"personas/{identity.id}/voice/sample.wav"
    storage.save(key, data)
    identity.voice_sample_path = key
    await _recompute_status(db, identity)
    await db.flush()
    await db.refresh(identity)

    warning = None
    duration = _probe_duration_seconds(data)
    if duration is not None and duration < _MIN_RECOMMENDED_VOICE_SECONDS:
        warning = (
            f"This clip is ~{duration:.0f}s. Voice cloning quality improves noticeably with "
            f"{_MIN_RECOMMENDED_VOICE_SECONDS:.0f}s+ of clean, continuous, single-speaker audio "
            "— consider uploading a longer sample."
        )
    return identity, warning


async def upload_reference_image(
    db: AsyncSession, identity_id: uuid.UUID, account_id: uuid.UUID,
    filename: str, data: bytes, mime: str | None,
) -> PersonaIdentity:
    identity = await get_identity(db, identity_id, account_id)
    if identity.status == PersonaIdentityStatus.revoked:
        raise ConflictError("This identity's consent was revoked.")
    if not data:
        raise RevOSError("Empty file.", code="empty_file", status_code=400)
    if len(data) > _MAX_IMAGE_BYTES:
        raise RevOSError("Image is too large (max 20MB).", code="file_too_large", status_code=400)
    if mime and not mime.startswith("image/"):
        raise RevOSError("Expected an image file.", code="invalid_mime", status_code=400)
    if len(identity.reference_image_paths) >= _MAX_REFERENCE_IMAGES:
        raise RevOSError(
            f"Maximum {_MAX_REFERENCE_IMAGES} reference images.", code="too_many_images", status_code=400,
        )

    storage = get_storage()
    digest = hashlib.sha256(data).hexdigest()[:12]
    key = f"personas/{identity.id}/images/{digest}_{filename}"
    storage.save(key, data)
    identity.reference_image_paths = [*identity.reference_image_paths, key]
    await _recompute_status(db, identity)
    await db.flush()
    await db.refresh(identity)
    return identity


async def remove_reference_image(
    db: AsyncSession, identity_id: uuid.UUID, account_id: uuid.UUID, path: str,
) -> PersonaIdentity:
    identity = await get_identity(db, identity_id, account_id)
    identity.reference_image_paths = [p for p in identity.reference_image_paths if p != path]
    await _recompute_status(db, identity)
    await db.flush()
    await db.refresh(identity)
    return identity


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------

async def grant_consent(
    db: AsyncSession, identity_id: uuid.UUID, account_id: uuid.UUID, user: AdminUser,
    *, subject_name: str, subject_email: str, consent_statement: str,
) -> PersonaConsent:
    identity = await get_identity(db, identity_id, account_id)
    if identity.status == PersonaIdentityStatus.revoked:
        raise ConflictError("This identity's consent was previously revoked.")
    existing = await _active_consent(db, identity_id)
    if existing is not None:
        raise ConflictError("This identity already has active consent on file.")
    if len(consent_statement.strip()) < 20:
        raise RevOSError(
            "Consent statement must be a substantive attestation, not a placeholder.",
            code="consent_too_short", status_code=400,
        )

    consent = PersonaConsent(
        account_id=account_id, persona_identity_id=identity_id,
        subject_name=subject_name.strip(), subject_email=subject_email.strip().lower(),
        consent_statement=consent_statement.strip(),
        policy_version=CURRENT_POLICY_VERSION,
        granted_by=user.id, granted_at=utcnow(), is_active=True,
    )
    db.add(consent)
    # The session is autoflush=False — _recompute_status queries for active
    # consent, so the insert above must be flushed first or it won't see it.
    await db.flush()
    await _recompute_status(db, identity)
    await db.flush()
    await db.refresh(consent)
    return consent


async def revoke_consent(
    db: AsyncSession, identity_id: uuid.UUID, account_id: uuid.UUID, user: AdminUser,
) -> PersonaIdentity:
    """Revoking consent immediately and permanently blocks reuse of this
    identity for generation. A fresh identity must be created if consent is
    later re-granted, so the audit trail of what was and wasn't consented is
    never ambiguous."""
    identity = await get_identity(db, identity_id, account_id)
    consent = await _active_consent(db, identity_id)
    if consent is not None:
        consent.is_active = False
        consent.revoked_at = utcnow()
        consent.revoked_by = user.id
        db.add(consent)
    identity.status = PersonaIdentityStatus.revoked
    db.add(identity)
    await db.flush()
    await db.refresh(identity)
    return identity


async def list_consents(db: AsyncSession, identity_id: uuid.UUID) -> list[PersonaConsent]:
    result = await db.execute(
        select(PersonaConsent).where(
            PersonaConsent.persona_identity_id == identity_id,
            PersonaConsent.deleted_at.is_(None),
        ).order_by(PersonaConsent.created_at.desc())
    )
    return list(result.scalars().all())


def is_usable_for_generation(identity: PersonaIdentity) -> bool:
    """Guard M3 (and any future caller) must check before running inference."""
    return identity.status == PersonaIdentityStatus.ready
