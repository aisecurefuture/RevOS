"""Bao (OpenBao / Vault) admin router.

Endpoints:
  GET /api/bao/status — owner-only status / health check
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.config import settings
from app.deps import CurrentUser, require_owner
from app.models.user import AdminUser
from app.services import secrets_service

logger = logging.getLogger("revos.bao")
router = APIRouter(prefix="/bao", tags=["secrets"])


@router.get("/status")
async def bao_status(
    _: AdminUser = Depends(require_owner),
) -> dict:
    """Return OpenBao reachability and configuration status.

    - ``configured``: True when ``BAO_TOKEN`` is set in the environment.
    - ``healthy``: True when OpenBao is reachable and unsealed.
    - ``addr``: The configured OpenBao address.

    This endpoint is read-only so no CSRF token is required.
    """
    configured = bool(settings.bao_token)
    healthy = False
    if configured:
        try:
            healthy = await secrets_service.is_healthy()
        except Exception:  # noqa: BLE001 — status must not raise
            healthy = False

    return {
        "healthy": healthy,
        "addr": settings.bao_addr,
        "configured": configured,
    }
