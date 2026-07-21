"""RevOS FastAPI application factory.

Wires middleware (CORS, security headers), exception handlers, and health
endpoints. Feature routers are registered as each module lands; the
`register_routers` function is the single integration point.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.request_limits import BodySizeLimitMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.database import async_engine

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("revos")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("RevOS starting in %s mode (debug=%s)", settings.app_env, settings.debug)
    logger.info("Integrations: %s", settings.integration_status())
    yield
    await async_engine.dispose()
    logger.info("RevOS shutdown complete")


def register_routers(app: FastAPI) -> None:
    """Mount feature routers. Populated incrementally by later modules."""
    from app.routers import (
        accounts,
        ai,
        analytics,
        approvals,
        auth,
        autopilot,
        automation,
        avatar_job,
        bao,
        billing,
        brand_book,
        brands,
        campaign_send,
        campaigns,
        companies,
        contacts,
        content,
        content_library,
        deals,
        email_templates,
        emails,
        forms,
        integration_credentials,
        integrations,
        landing_pages,
        leads,
        listing_video,
        matching,
        media,
        notes_tasks,
        offers,
        persona_identity,
        pitch_video,
        platform_admin,
        public,
        public_scheduler,
        scheduler,
        sequences,
        social,
        social_comments,
        social_oauth,
        suppressions,
        video_script,
        webhooks,
    )

    app.include_router(auth.router, prefix="/api")
    app.include_router(accounts.router, prefix="/api")
    app.include_router(platform_admin.router, prefix="/api")
    app.include_router(billing.router, prefix="/api")
    app.include_router(bao.router, prefix="/api")
    app.include_router(brands.router, prefix="/api")
    app.include_router(brand_book.router, prefix="/api")
    app.include_router(offers.router, prefix="/api")
    app.include_router(campaigns.router, prefix="/api")
    app.include_router(campaign_send.router, prefix="/api")
    app.include_router(forms.router, prefix="/api")
    app.include_router(landing_pages.router, prefix="/api")
    app.include_router(leads.router, prefix="/api")
    app.include_router(public.router, prefix="/api")
    app.include_router(emails.router, prefix="/api")
    app.include_router(email_templates.router, prefix="/api")
    app.include_router(suppressions.router, prefix="/api")
    app.include_router(video_script.router, prefix="/api")
    app.include_router(sequences.router, prefix="/api")
    app.include_router(approvals.router, prefix="/api")
    app.include_router(automation.router, prefix="/api")
    app.include_router(autopilot.router, prefix="/api")
    app.include_router(avatar_job.router, prefix="/api")
    app.include_router(webhooks.router, prefix="/api")
    app.include_router(contacts.router, prefix="/api")
    app.include_router(companies.router, prefix="/api")
    app.include_router(deals.router, prefix="/api")
    app.include_router(notes_tasks.notes_router, prefix="/api")
    app.include_router(notes_tasks.tasks_router, prefix="/api")
    app.include_router(content.router, prefix="/api")
    app.include_router(content_library.router, prefix="/api")
    app.include_router(social.router, prefix="/api")
    app.include_router(social_comments.router, prefix="/api")
    app.include_router(social_oauth.router, prefix="/api")
    app.include_router(media.router, prefix="/api")
    app.include_router(matching.router, prefix="/api")
    app.include_router(analytics.router, prefix="/api")
    app.include_router(integrations.router, prefix="/api")
    app.include_router(integration_credentials.router, prefix="/api")
    app.include_router(scheduler.router, prefix="/api")
    app.include_router(public_scheduler.router, prefix="/api")
    app.include_router(persona_identity.router, prefix="/api")
    app.include_router(pitch_video.router, prefix="/api")
    app.include_router(listing_video.router, prefix="/api")
    app.include_router(ai.router, prefix="/api")


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} API",
        description="Approval-first marketing & sales automation platform.",
        version="0.1.0",
        lifespan=lifespan,
        # Hide interactive docs in production.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
    )

    # --- Middleware (order matters: security headers wrap everything) --------
    # Rate limiting is enforced per-route via the rate_limit dependency
    # (app.core.rate_limit); RateLimitError uses the standard error envelope.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    )

    register_exception_handlers(app)
    register_routers(app)

    # --- Health / readiness -------------------------------------------------
    @app.get("/health/live", tags=["health"])
    async def liveness() -> dict:
        """Process is up. Used by container/orchestrator liveness probes."""
        return {"status": "ok", "app": settings.app_name, "env": settings.app_env}

    @app.get("/health/ready", tags=["health"])
    async def readiness() -> dict:
        """Dependencies reachable. Reports DB connectivity + integration status."""
        db_ok = True
        try:
            async with async_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001 — readiness must not raise
            logger.exception("Readiness DB check failed")
            db_ok = False
        return {
            "status": "ok" if db_ok else "degraded",
            "database": db_ok,
            "integrations": settings.integration_status(),
        }

    @app.get("/", tags=["health"])
    async def root() -> dict:
        return {
            "name": settings.app_name,
            "version": "0.1.0",
            "docs": None if settings.is_production else "/docs",
        }

    return app


app = create_app()
