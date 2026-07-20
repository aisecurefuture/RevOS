"""Stock XTTS speaker list — shared by Pitch Video + Listing Video studios.

The list is static per model version, but computing it is expensive (the
avatar-worker shells into the XTTS venv and loads the model — tens of
seconds). So it's resolved in tiers and persisted write-through:

  1. PITCH_VIDEO_VOICES env allowlist (instant, operator-pinned)
  2. process cache
  3. a backend in THIS process (dev/tests with the stub)
  4. the storage snapshot the worker wrote on its first enumeration
  5. (optional) a short live ask of the avatar-worker; its task ALSO writes
     the storage snapshot, so a first-ever miss self-heals for every later
     request even if this one times out.

``resolve(ask_worker=False)`` never blocks on the worker — that's the mode
used for request-path validation.
"""

from __future__ import annotations

import json
import logging

from app.config import settings
from app.services.avatar.inference import get_backend
from app.services.storage_service import get_storage

logger = logging.getLogger("revos.stock_voices")

STORAGE_KEY = "pitch-videos/stock-speakers.json"

_cache: list[str] | None = None


def save_snapshot(speakers: list[str]) -> None:
    """Persist the worker-computed list so the API never needs a live ask."""
    try:
        get_storage().save(STORAGE_KEY, json.dumps(speakers).encode())
    except Exception:  # noqa: BLE001 — snapshot is an optimization, never fatal
        logger.exception("Could not persist stock speaker snapshot")


def _read_snapshot() -> list[str]:
    try:
        storage = get_storage()
        if storage.exists(STORAGE_KEY):
            data = json.loads(storage.read(STORAGE_KEY))
            if isinstance(data, list):
                return [str(s) for s in data]
    except Exception:  # noqa: BLE001
        logger.exception("Could not read stock speaker snapshot")
    return []


async def resolve(*, ask_worker: bool = True) -> list[str]:
    """The known stock voices, [] when nothing is reachable (fail open)."""
    global _cache

    if settings.pitch_video_voices:
        return [v.strip() for v in settings.pitch_video_voices.split(",") if v.strip()]
    if _cache is not None:
        return _cache

    backend = get_backend()
    if backend is not None and backend.available and hasattr(backend, "list_stock_speakers"):
        try:
            _cache = backend.list_stock_speakers()
            return _cache
        except Exception:  # noqa: BLE001 — fall through to snapshot/worker
            logger.exception("In-process speaker enumeration failed")

    snapshot = _read_snapshot()
    if snapshot:
        _cache = snapshot
        return snapshot

    if not ask_worker:
        return []

    import asyncio

    def _ask() -> list[str]:
        from app.workers.celery_app import celery_app
        # Short timeout: this can run inline in a page-load request. Even on
        # timeout the task keeps running on the worker and writes the storage
        # snapshot, so the NEXT request resolves instantly from tier 4.
        return celery_app.send_task("pitch_video.list_speakers").get(timeout=6)

    try:
        speakers = await asyncio.to_thread(_ask)
    except Exception:  # noqa: BLE001 — worker down/slow: degrade, don't 500
        return []
    if speakers:
        _cache = speakers
    return speakers or []
