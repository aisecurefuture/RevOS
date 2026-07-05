"""Per-account low-cost integration credentials (Phase 3).

Each provider stores non-secret config on the row and any actual secret in
OpenBao at ``revos/accounts/{account_id}/integrations/{provider}``. Secrets are
never returned by list/get — only ``connect``/``regenerate`` calls that mint a
fresh Zapier inbound secret return it once, mirroring the 2FA recovery-code
pattern (shown once, never again).
"""

from __future__ import annotations

import secrets as _secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, RevOSError
from app.models.integration_credential import (
    IntegrationCredential,
    IntegrationCredentialStatus,
    IntegrationProvider,
)
from app.models.user import AdminUser
from app.services import secrets_service
from app.services.integrations import google_sheets as sheets_client


def _secret_path(account_id: uuid.UUID, provider: str) -> str:
    return f"revos/accounts/{account_id}/integrations/{provider}"


async def get_credential(
    db: AsyncSession, account_id: uuid.UUID, provider: IntegrationProvider
) -> IntegrationCredential | None:
    result = await db.execute(
        select(IntegrationCredential).where(
            IntegrationCredential.account_id == account_id,
            IntegrationCredential.provider == provider,
            IntegrationCredential.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def list_credentials(db: AsyncSession, account_id: uuid.UUID) -> list[IntegrationCredential]:
    result = await db.execute(
        select(IntegrationCredential).where(
            IntegrationCredential.account_id == account_id,
            IntegrationCredential.deleted_at.is_(None),
        )
    )
    return list(result.scalars().all())


async def get_secret_data(cred: IntegrationCredential) -> dict | None:
    """Read the secret payload for a credential. None if it has none (Calendly)."""
    if not cred.secret_ref:
        return None
    return await secrets_service.get_secret(cred.secret_ref)


async def _upsert(
    db: AsyncSession, account_id: uuid.UUID, provider: IntegrationProvider,
    config: dict, secret_ref: str | None, user: AdminUser,
) -> IntegrationCredential:
    existing = await get_credential(db, account_id, provider)
    if existing is not None:
        existing.config = config
        existing.secret_ref = secret_ref
        existing.status = IntegrationCredentialStatus.active
        existing.connected_by = user.id
        db.add(existing)
        await db.flush()
        await db.refresh(existing)
        return existing
    cred = IntegrationCredential(
        account_id=account_id, provider=provider, config=config,
        secret_ref=secret_ref, connected_by=user.id,
    )
    db.add(cred)
    await db.flush()
    await db.refresh(cred)
    return cred


async def save_calendly(
    db: AsyncSession, account_id: uuid.UUID, scheduling_url: str, user: AdminUser
) -> IntegrationCredential:
    if not scheduling_url.strip():
        raise RevOSError("A scheduling URL is required.", code="invalid_config", status_code=400)
    return await _upsert(
        db, account_id, IntegrationProvider.calendly,
        {"scheduling_url": scheduling_url.strip()}, None, user,
    )


async def save_notion(
    db: AsyncSession, account_id: uuid.UUID, api_key: str, database_id: str, user: AdminUser
) -> IntegrationCredential:
    if not api_key.strip() or not database_id.strip():
        raise RevOSError("An API key and database ID are both required.", code="invalid_config", status_code=400)
    path = _secret_path(account_id, "notion")
    await secrets_service.put_secret(path, {"api_key": api_key.strip()})
    return await _upsert(
        db, account_id, IntegrationProvider.notion,
        {"database_id": database_id.strip()}, path, user,
    )


async def save_bitly(
    db: AsyncSession, account_id: uuid.UUID, access_token: str, user: AdminUser
) -> IntegrationCredential:
    if not access_token.strip():
        raise RevOSError("An access token is required.", code="invalid_config", status_code=400)
    path = _secret_path(account_id, "bitly")
    await secrets_service.put_secret(path, {"access_token": access_token.strip()})
    return await _upsert(db, account_id, IntegrationProvider.bitly, {}, path, user)


async def save_google_sheets(
    db: AsyncSession, account_id: uuid.UUID, service_account_json: str, spreadsheet_id: str, user: AdminUser
) -> IntegrationCredential:
    if not spreadsheet_id.strip():
        raise RevOSError("A spreadsheet ID is required.", code="invalid_config", status_code=400)
    # Validates the JSON shape up front so a bad paste fails fast, not on first push.
    sheets_client.parse_service_account(service_account_json)
    path = _secret_path(account_id, "google_sheets")
    await secrets_service.put_secret(path, {"service_account_json": service_account_json})
    return await _upsert(
        db, account_id, IntegrationProvider.google_sheets,
        {"spreadsheet_id": spreadsheet_id.strip()}, path, user,
    )


async def save_zapier(
    db: AsyncSession, account_id: uuid.UUID, outbound_webhook_url: str | None, user: AdminUser
) -> tuple[IntegrationCredential, str | None]:
    """Save (or update) the Zapier config. Generates a fresh inbound signing
    secret on first save only — returned once (the caller must show it to the
    user immediately; it is never retrievable again). Returns
    (credential, new_secret_or_None)."""
    existing = await get_credential(db, account_id, IntegrationProvider.zapier)
    path = _secret_path(account_id, "zapier")
    new_secret: str | None = None
    if existing is None:
        new_secret = _secrets.token_urlsafe(32)
        await secrets_service.put_secret(path, {"inbound_secret": new_secret})
    config = {"outbound_webhook_url": (outbound_webhook_url or "").strip() or None}
    cred = await _upsert(db, account_id, IntegrationProvider.zapier, config, path, user)
    return cred, new_secret


async def regenerate_zapier_secret(
    db: AsyncSession, account_id: uuid.UUID, user: AdminUser
) -> str:
    """Rotate the inbound signing secret. Old value stops working immediately."""
    cred = await get_credential(db, account_id, IntegrationProvider.zapier)
    if cred is None:
        raise NotFoundError("Zapier is not configured for this account.")
    path = _secret_path(account_id, "zapier")
    new_secret = _secrets.token_urlsafe(32)
    await secrets_service.put_secret(path, {"inbound_secret": new_secret})
    cred.connected_by = user.id
    db.add(cred)
    await db.flush()
    return new_secret


async def get_zapier_inbound_secret(db: AsyncSession, account_id: uuid.UUID) -> str | None:
    cred = await get_credential(db, account_id, IntegrationProvider.zapier)
    if cred is None or not cred.secret_ref:
        return None
    data = await secrets_service.get_secret(cred.secret_ref)
    return data.get("inbound_secret") if data else None


async def delete_credential(
    db: AsyncSession, account_id: uuid.UUID, provider: IntegrationProvider
) -> None:
    cred = await get_credential(db, account_id, provider)
    if cred is None:
        raise NotFoundError(f"{provider} is not configured for this account.")
    if cred.secret_ref:
        try:
            await secrets_service.delete_secret(cred.secret_ref)
        except RevOSError:
            pass  # best-effort — don't block removal if Bao is unavailable
    from app.models.base import utcnow
    cred.deleted_at = utcnow()
    db.add(cred)
    await db.flush()
