"""Public, unauthenticated lead-capture surface.

Endpoints here are rate-limited and never require a session. They power hosted
landing pages, embeddable forms, form submission, double-opt-in confirmation,
and one-click unsubscribe. Submissions accept JSON (embeds/SPA) or
form-urlencoded (hosted/iframe forms).
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.core.exceptions import ComplianceError, NotFoundError
from app.core.net import client_ip as _client_ip
from app.core.rate_limit import rate_limit
from app.core.tenancy import set_active_account
from app.deps import DbSession
from app.models.campaign import Form, FormSubmission
from app.schemas.analytics import TrackEventRequest
from app.services import (
    consent_service,
    event_service,
    form_service,
    integrations_service,
    landing_service,
    public_render,
    utm_service,
)

router = APIRouter(prefix="/public", tags=["public"])

# Per-IP throttle for the public surface (anti-abuse).
_submit_limit = rate_limit("public_submit", "30/minute")
# Read endpoints (render/redirect) that also write — looser, but still bounded.
_read_limit = rate_limit("public_read", "120/minute")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_KNOWN = {"email", "first_name", "last_name", "phone", "company_name",
          "consent", "hp", "referrer"}

# Landing pages: standalone, no framing, inline styles only, no scripts.
_LANDING_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; img-src https: data:; style-src 'unsafe-inline'; "
        "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
    ),
    "X-Frame-Options": "DENY",
}
# Embeddable forms: same, but iframe-able from any site.
_EMBED_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; img-src https: data:; style-src 'unsafe-inline'; "
        "form-action 'self'; base-uri 'none'; frame-ancestors *"
    ),
}


def _truthy(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "on", "yes"} if value is not None else False




async def _parse_body(request: Request) -> tuple[dict, bool]:
    """Return (data, is_json) from a JSON or form-urlencoded request body."""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            return await request.json(), True
        except Exception:  # noqa: BLE001
            return {}, True
    form = await request.form()
    return dict(form), False


@router.post("/forms/{slug}/submit")
async def submit_form(
    slug: str, request: Request, db: DbSession, _rl: None = Depends(_submit_limit)
):
    form = await form_service.get_public_form(db, slug)
    if form is None:
        raise NotFoundError("Form not found.")
    # Public path has no auth context: bind writes to the form's account so the
    # lead/contact/submission land in the right tenant (not as orphans).
    set_active_account(form.account_id)

    data, is_json = await _parse_body(request)
    ip, ua = _client_ip(request), request.headers.get("user-agent", "")[:400]

    # Honeypot: silently accept bots without processing, to avoid tipping them off.
    if str(data.get("hp") or "").strip():
        db.add(FormSubmission(form_id=form.id, brand_id=form.brand_id,
                              data={}, is_spam=True, processed=True, ip_address=ip))
        await db.flush()
        return _respond(is_json, {"status": "ok", "message": "Thanks!",
                                  "requires_confirmation": False, "redirect_url": form.redirect_url})

    email = str(data.get("email") or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise ComplianceError("A valid email address is required.")

    utm = {k: v for k, v in data.items() if k.startswith("utm_")}
    extra = {k: v for k, v in data.items()
             if k not in _KNOWN and not k.startswith("utm_")}

    result = await consent_service.process_submission(
        db, form, email=email,
        first_name=data.get("first_name"), last_name=data.get("last_name"),
        phone=data.get("phone"), company_name=data.get("company_name"),
        consent=_truthy(data.get("consent")), utm=utm,
        referrer=data.get("referrer"), extra=extra, ip=ip, ua=ua,
    )
    await _fire_zapier_new_lead(db, form, email, data)
    return _respond(is_json, result)


async def _fire_zapier_new_lead(db: DbSession, form: Form, email: str, data: dict) -> None:
    """Best-effort Zapier/Make outbound event on a new form submission. Never
    raises — a webhook outage must not break the public submission response."""
    try:
        from app.models.integration_credential import IntegrationProvider
        from app.services import integration_credentials_service

        cred = await integration_credentials_service.get_credential(
            db, form.account_id, IntegrationProvider.zapier,
        )
        url = (cred.config.get("outbound_webhook_url") if cred else None)
        if not url:
            return
        await integrations_service.dispatch_outbound(url, {
            "event": "new_lead", "form_id": str(form.id), "brand_id": str(form.brand_id),
            "email": email, "first_name": data.get("first_name"), "last_name": data.get("last_name"),
        })
    except Exception:  # noqa: BLE001 — best-effort side channel
        pass


def _respond(is_json: bool, result: dict):
    if is_json:
        return JSONResponse(result)
    if result.get("redirect_url"):
        return RedirectResponse(result["redirect_url"], status_code=303)
    title = "Almost there" if result.get("requires_confirmation") else "Thank you"
    return HTMLResponse(public_render.render_notice(title, result["message"]))


@router.get("/confirm", response_class=HTMLResponse)
async def confirm(token: str, db: DbSession) -> HTMLResponse:
    await consent_service.confirm_double_optin(db, token)
    return HTMLResponse(public_render.render_notice(
        "Subscription confirmed", "Thanks for confirming — you’re all set."),
        headers=_LANDING_HEADERS)


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(token: str, db: DbSession) -> HTMLResponse:
    await consent_service.unsubscribe(db, token)
    return HTMLResponse(public_render.render_notice(
        "Unsubscribed", "You’ve been removed and won’t receive further emails."),
        headers=_LANDING_HEADERS)


@router.get("/forms/{slug}", response_class=HTMLResponse)
async def render_form(slug: str, request: Request, db: DbSession,
                      _rl: None = Depends(_read_limit)) -> HTMLResponse:
    form = await form_service.get_public_form(db, slug)
    if form is None or not form.embed_enabled:
        raise NotFoundError("Form not found.")
    utm = {k: v for k, v in request.query_params.items() if k.startswith("utm_")}
    action = f"/api/public/forms/{form.slug}/submit"
    return HTMLResponse(
        public_render.render_form_page(form, action=action, utm=utm), headers=_EMBED_HEADERS
    )


@router.post("/track")
async def track(
    body: TrackEventRequest, request: Request, db: DbSession,
    _rl: None = Depends(_submit_limit),
) -> dict:
    """First-party event ingest (page views, custom events). Privacy-friendly."""
    await event_service.track_event(
        db, name=body.name, brand_id=body.brand_id, properties=body.properties,
        utm=body.utm, ip=_client_ip(request), session_id=body.session_id)
    return {"ok": True}


@router.get("/u/{code}")
async def utm_redirect(code: str, db: DbSession,
                       _rl: None = Depends(_read_limit)) -> RedirectResponse:
    link = await utm_service.get_by_code(db, code)
    if link is None:
        raise NotFoundError("Link not found.")
    target = await utm_service.track_click(db, link)
    return RedirectResponse(target, status_code=307)


@router.get("/p/{slug}", response_class=HTMLResponse)
async def render_landing(slug: str, request: Request, db: DbSession,
                         _rl: None = Depends(_read_limit)) -> HTMLResponse:
    page = await landing_service.get_published_page(db, slug)
    if page is None:
        raise NotFoundError("Page not found.")
    await event_service.track_event(db, name="page_view", brand_id=page.brand_id,
                                    properties={"slug": slug}, ip=_client_ip(request))
    form = None
    if page.form_id:
        form = await db.get(Form, page.form_id)
    utm = {k: v for k, v in request.query_params.items() if k.startswith("utm_")}
    action = f"/api/public/forms/{form.slug}/submit" if form else "#"
    return HTMLResponse(
        public_render.render_landing(page, form, action=action, utm=utm),
        headers=_LANDING_HEADERS,
    )
