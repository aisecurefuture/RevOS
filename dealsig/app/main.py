from __future__ import annotations

import base64
import hashlib
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

from email_validator import EmailNotValidError, validate_email
from fastapi import BackgroundTasks, Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import get_settings
from app.database import SessionLocal, get_db, init_db
from app.models import Listing, PasskeyCredential, RefreshRun, SavedListing, SourceStatus, User
from app.security import (
    SecurityHeadersMiddleware,
    client_key,
    get_csrf_token,
    rate_limiter,
    verify_csrf,
)
from app.services import authentication, billing, challenge, contact, passkeys
from app.services.refresh import refresh_all, refresh_source, rescore_listing
from app.services.seeds import seed_database
from app.services.sources import SOURCE_BY_SLUG

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger("dealsig.web")


def format_money(value) -> str:
    if value is None:
        return "—"
    return f"${Decimal(value):,.0f}"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def format_date(value) -> str:
    if not value:
        return "Not posted"
    if isinstance(value, str):
        return value
    # Stored timestamps are UTC. Emit the machine-readable instant alongside a
    # UTC-labelled fallback; app.js rewrites the text into the viewer's own
    # timezone, so a reader in Chicago is never shown a GMT clock time.
    moment = _aware(value)
    return Markup('<time datetime="{iso}">{text}</time>').format(
        iso=moment.isoformat(),
        text=moment.strftime("%b %d, %Y · %-I:%M %p UTC"),
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:
        seed_database(db)
    yield


app = FastAPI(
    title="DealSig AI",
    version="0.1.0",
    docs_url="/api/docs" if settings.app_env != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.host_list)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="dealsig_session",
    max_age=60 * 60 * 24 * 14,
    same_site=settings.cookie_same_site,
    https_only=settings.cookie_secure,
)
app.add_middleware(SecurityHeadersMiddleware)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.filters["money"] = format_money
templates.env.filters["date"] = format_date


def current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    return db.get(User, user_id) if user_id else None


def require_user(request: Request, db: Session) -> User:
    user = current_user(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required")
    return user


def require_member(request: Request, db: Session) -> User:
    user = require_user(request, db)
    if not user.has_access:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Membership required")
    return user


def page_context(request: Request, db: Session, **values) -> dict:
    return {
        "request": request,
        "user": current_user(request, db),
        "csrf_token": get_csrf_token(request),
        "demo_mode": settings.demo_mode,
        "sso": authentication.configured_sso(),
        "auth_code_ttl_minutes": settings.auth_code_ttl_minutes,
        "now": datetime.now(timezone.utc),
        **values,
    }


def safe_redirect_path(path: str | None, fallback: str = "/app") -> str:
    if not path:
        return fallback
    parsed = urlparse(path)
    return path if not parsed.scheme and not parsed.netloc and path.startswith("/") else fallback


def wants_json(request: Request) -> bool:
    """/api/* is only ever called by fetch(), which chokes on an HTML body."""
    return request.url.path.startswith("/api/")


@app.exception_handler(401)
async def unauthorized_handler(request: Request, exc: HTTPException):
    if wants_json(request):
        return JSONResponse({"detail": exc.detail or "Sign in required"}, status_code=401)
    return RedirectResponse(f"/login?next={request.url.path}", status_code=303)


@app.exception_handler(402)
async def paywall_handler(request: Request, exc: HTTPException):
    if wants_json(request):
        return JSONResponse(
            {"detail": exc.detail or "DealSig Pro is required for this.", "upgrade_url": "/billing"},
            status_code=402,
        )
    with SessionLocal() as db:
        return templates.TemplateResponse(
            request,
            "billing.html",
            page_context(request, db, paywall=True, error="This analysis is included with DealSig Pro."),
            status_code=402,
        )


@app.get("/", response_class=HTMLResponse)
def landing(request: Request, db: Session = Depends(get_db)):
    listing_count = db.scalar(select(func.count()).select_from(Listing)) or 0
    source_count = db.scalar(select(func.count()).select_from(SourceStatus)) or 0
    return templates.TemplateResponse(
        request,
        "landing.html",
        page_context(request, db, listing_count=listing_count, source_count=source_count),
    )


@app.get("/brand-logo.png", include_in_schema=False)
def brand_logo():
    """Serve the user-supplied brand asset without duplicating or modifying it."""
    return FileResponse(BASE_DIR.parent / "DealSigAI.PNG", media_type="image/png")


@app.get("/brand-logo-dark.png", include_in_schema=False)
def brand_logo_dark():
    """Serve the user-supplied dark-background brand asset."""
    return FileResponse(BASE_DIR.parent / "DealSigAI_Dark.PNG", media_type="image/png")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "auth.html",
        page_context(
            request,
            db,
            mode="login",
            next=request.query_params.get("next", "/app"),
            error=request.query_params.get("error", ""),
        ),
    )


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "auth.html", page_context(request, db, mode="register", next="/billing")
    )


@app.post("/auth/code/request")
async def request_email_code(
    request: Request,
    email: str = Form(...),
    next: str = Form("/app"),
    db: Session = Depends(get_db),
):
    await verify_csrf(request)
    rate_limiter.check(client_key(request, "email-code-ip"), 10, 3600)
    try:
        normalized = validate_email(email, check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        return templates.TemplateResponse(
            request,
            "auth.html",
            page_context(request, db, mode="login", next=next, error="Enter a valid email address."),
            status_code=400,
        )
    email_key = hashlib.sha256(normalized.encode()).hexdigest()[:20]
    rate_limiter.check(f"email-code-address:{email_key}", 4, 900)
    code = authentication.create_email_code(
        db,
        normalized,
        request.client.host if request.client else "unknown",
    )
    delivery_error = ""
    try:
        await authentication.send_email_code(normalized, code)
    except Exception as exc:
        logger.warning("Resend login-code delivery failed (%s)", type(exc).__name__)
        delivery_error = (
            "Email delivery is not configured yet. Add a Resend API key, or use the product demo."
            if settings.demo_mode
            else "We could not send a code right now. Please try again shortly."
        )
    request.session["auth_email"] = normalized
    request.session["auth_next"] = safe_redirect_path(next)
    return templates.TemplateResponse(
        request,
        "auth.html",
        page_context(
            request,
            db,
            mode="verify",
            email=normalized,
            next=safe_redirect_path(next),
            delivery_error=delivery_error,
            demo_code=code if settings.demo_mode and not settings.resend_api_key else "",
        ),
        status_code=503 if delivery_error and not settings.demo_mode else 200,
    )


@app.post("/auth/code/verify")
async def verify_email_code_route(
    request: Request,
    email: str = Form(...),
    code: str = Form(...),
    next: str = Form("/app"),
    db: Session = Depends(get_db),
):
    await verify_csrf(request)
    rate_limiter.check(client_key(request, "verify-code"), 20, 900)
    user = authentication.verify_email_code(db, email, code)
    if not user:
        return templates.TemplateResponse(
            request,
            "auth.html",
            page_context(
                request,
                db,
                mode="verify",
                email=email,
                next=safe_redirect_path(next),
                error="That code is invalid or expired. Request a new code if needed.",
            ),
            status_code=400,
        )
    request.session.clear()
    request.session["user_id"] = user.id
    get_csrf_token(request)
    return RedirectResponse(safe_redirect_path(next), status_code=303)


@app.get("/auth/sso/{provider_name}")
async def sso_start(provider_name: str, request: Request):
    if provider_name not in {"google", "microsoft", "apple"}:
        raise HTTPException(status_code=404)
    provider = authentication.oauth.create_client(provider_name)
    if not provider:
        return RedirectResponse("/login?error=That+identity+provider+is+not+configured", status_code=303)
    redirect_uri = f"{settings.base_url}/auth/sso/{provider_name}/callback"
    parameters = {"code_challenge_method": "S256"}
    if provider_name == "apple":
        parameters["response_mode"] = "form_post"
    return await provider.authorize_redirect(request, redirect_uri, **parameters)


@app.api_route("/auth/sso/{provider_name}/callback", methods=["GET", "POST"])
async def sso_callback(provider_name: str, request: Request, db: Session = Depends(get_db)):
    if provider_name not in {"google", "microsoft", "apple"}:
        raise HTTPException(status_code=404)
    provider = authentication.oauth.create_client(provider_name)
    if not provider:
        raise HTTPException(status_code=404)
    try:
        token = await provider.authorize_access_token(request)
        claims = dict(token.get("userinfo") or {})
        if not claims:
            raise ValueError("Identity provider did not return verified OpenID claims")
        user = authentication.resolve_sso_user(db, provider_name, claims)
    except Exception:
        return templates.TemplateResponse(
            request,
            "auth.html",
            page_context(
                request,
                db,
                mode="login",
                next="/app",
                error="Single sign-on could not be completed. Try an email code or another provider.",
            ),
            status_code=400,
        )
    request.session.clear()
    request.session["user_id"] = user.id
    get_csrf_token(request)
    return RedirectResponse("/app", status_code=303)


def _challenge_to_session(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _challenge_from_session(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@app.post("/api/passkeys/auth/options")
async def passkey_auth_options(request: Request, db: Session = Depends(get_db)):
    await verify_csrf(request)
    rate_limiter.check(client_key(request, "passkey-options"), 20, 300)
    if not db.scalar(select(func.count()).select_from(PasskeyCredential)):
        raise HTTPException(status_code=404, detail="No passkeys are registered yet")
    options_json, challenge = passkeys.authentication_options()
    request.session["passkey_auth_challenge"] = _challenge_to_session(challenge)
    return JSONResponse(content=json.loads(options_json))


@app.post("/api/passkeys/auth/verify")
async def passkey_auth_verify(request: Request, db: Session = Depends(get_db)):
    await verify_csrf(request)
    encoded_challenge = request.session.pop("passkey_auth_challenge", "")
    if not encoded_challenge:
        raise HTTPException(status_code=400, detail="Passkey challenge expired")
    try:
        user = passkeys.verify_authentication(
            db, await request.json(), _challenge_from_session(encoded_challenge)
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Passkey verification failed") from exc
    request.session.clear()
    request.session["user_id"] = user.id
    get_csrf_token(request)
    return {"status": "authenticated", "redirect": "/app"}


@app.post("/api/passkeys/register/options")
async def passkey_register_options(request: Request, db: Session = Depends(get_db)):
    await verify_csrf(request)
    user = require_user(request, db)
    options_json, challenge = passkeys.registration_options(db, user)
    request.session["passkey_registration_challenge"] = _challenge_to_session(challenge)
    return JSONResponse(content=json.loads(options_json))


@app.post("/api/passkeys/register/verify")
async def passkey_register_verify(request: Request, db: Session = Depends(get_db)):
    await verify_csrf(request)
    user = require_user(request, db)
    encoded_challenge = request.session.pop("passkey_registration_challenge", "")
    if not encoded_challenge:
        raise HTTPException(status_code=400, detail="Passkey challenge expired")
    try:
        passkeys.verify_registration(
            db, user, await request.json(), _challenge_from_session(encoded_challenge)
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Passkey registration failed") from exc
    return {"status": "registered"}


@app.get("/settings/security", response_class=HTMLResponse)
def security_settings(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    credentials = list(
        db.scalars(
            select(PasskeyCredential)
            .where(PasskeyCredential.user_id == user.id)
            .order_by(PasskeyCredential.created_at.desc())
        )
    )
    return templates.TemplateResponse(
        request,
        "security_settings.html",
        page_context(
            request,
            db,
            active_page="security",
            credentials=credentials,
        ),
    )


@app.post("/logout")
async def logout(request: Request):
    await verify_csrf(request)
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@app.post("/demo")
async def demo_login(request: Request, db: Session = Depends(get_db)):
    await verify_csrf(request)
    if not settings.demo_mode:
        raise HTTPException(status_code=404)
    rate_limiter.check(client_key(request, "demo"), 20, 60)
    user = db.scalar(select(User).where(User.email == "demo@dealsig.ai"))
    if not user:
        raise HTTPException(status_code=503, detail="Demo account not initialized")
    request.session.clear()
    request.session["user_id"] = user.id
    get_csrf_token(request)
    return RedirectResponse("/app", status_code=303)


@app.get("/app", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    listings = list(
        db.scalars(
            select(Listing)
            .where(Listing.status == "open")
            .order_by(desc(Listing.deal_score), Listing.auction_end)
            .limit(6)
        )
    )
    sources = list(db.scalars(select(SourceStatus).order_by(SourceStatus.name)))
    total = db.scalar(select(func.count()).select_from(Listing).where(Listing.status == "open")) or 0
    new_count = sum(
        1 for item in listings if (datetime.now(timezone.utc) - _aware(item.first_seen_at)).days < 1
    )
    upcoming = sorted(
        (item for item in listings if item.auction_end),
        key=lambda item: _aware(item.auction_end),
    )[:3]
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        page_context(
            request,
            db,
            active_page="dashboard",
            listings=listings,
            sources=sources,
            total=total,
            new_count=new_count,
            upcoming=upcoming,
            user=user,
        ),
    )


@app.get("/deals", response_class=HTMLResponse)
def deals(
    request: Request,
    q: str = "",
    county: str = "",
    source: str = "",
    instrument: str = "",
    sort: str = "score",
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    query = select(Listing).where(Listing.status == "open")
    if q:
        pattern = f"%{q[:100]}%"
        query = query.where(
            or_(Listing.title.ilike(pattern), Listing.city.ilike(pattern), Listing.county.ilike(pattern))
        )
    if county:
        query = query.where(Listing.county == county[:120])
    if source:
        query = query.where(Listing.source == source[:64])
    if instrument:
        query = query.where(Listing.instrument_type == instrument[:80])
    if sort == "deadline":
        query = query.order_by(Listing.auction_end.asc().nullslast())
    elif sort == "profit":
        query = query.order_by(Listing.estimated_profit.desc().nullslast())
    else:
        query = query.order_by(desc(Listing.deal_score), Listing.auction_end)
    listings = list(db.scalars(query.limit(200)))
    counties = list(db.scalars(select(Listing.county).distinct().where(Listing.county != "").order_by(Listing.county)))
    sources = list(db.scalars(select(SourceStatus).order_by(SourceStatus.name)))
    saved_ids = set(db.scalars(select(SavedListing.listing_id).where(SavedListing.user_id == user.id)))
    return templates.TemplateResponse(
        request,
        "deals.html",
        page_context(
            request,
            db,
            active_page="deals",
            listings=listings,
            counties=counties,
            sources=sources,
            saved_ids=saved_ids,
            filters={"q": q, "county": county, "source": source, "instrument": instrument, "sort": sort},
        ),
    )


@app.get("/deals/{listing_id}", response_class=HTMLResponse)
def deal_detail(listing_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_member(request, db)
    listing = db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status_code=404)
    saved = db.scalar(
        select(SavedListing).where(
            SavedListing.user_id == user.id, SavedListing.listing_id == listing.id
        )
    )
    source = db.get(SourceStatus, listing.source)
    return templates.TemplateResponse(
        request,
        "deal_detail.html",
        page_context(
            request,
            db,
            active_page="deals",
            listing=listing,
            source=source,
            saved=bool(saved),
            score_factors=json.dumps(listing.score_factors or {}, indent=2),
        ),
    )


@app.post("/deals/{listing_id}/save")
async def toggle_save(listing_id: int, request: Request, db: Session = Depends(get_db)):
    await verify_csrf(request)
    user = require_member(request, db)
    listing = db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status_code=404)
    saved = db.scalar(
        select(SavedListing).where(
            SavedListing.user_id == user.id, SavedListing.listing_id == listing_id
        )
    )
    if saved:
        db.delete(saved)
        state = "removed"
    else:
        db.add(SavedListing(user_id=user.id, listing_id=listing_id))
        state = "saved"
    db.commit()
    if request.headers.get("accept") == "application/json":
        return {"status": state}
    return RedirectResponse(safe_redirect_path(request.headers.get("referer"), f"/deals/{listing_id}"), status_code=303)


@app.get("/watchlist", response_class=HTMLResponse)
def watchlist(request: Request, db: Session = Depends(get_db)):
    user = require_member(request, db)
    listings = list(
        db.scalars(
            select(Listing)
            .join(SavedListing, SavedListing.listing_id == Listing.id)
            .where(SavedListing.user_id == user.id)
            .order_by(desc(Listing.deal_score))
        )
    )
    return templates.TemplateResponse(
        request,
        "deals.html",
        page_context(
            request,
            db,
            active_page="watchlist",
            listings=listings,
            counties=[],
            sources=[],
            saved_ids={item.id for item in listings},
            filters={"q": "", "county": "", "source": "", "instrument": "", "sort": "score"},
            watchlist_mode=True,
        ),
    )


@app.post("/api/listings/{listing_id}/analyze")
async def analyze_listing(listing_id: int, request: Request, db: Session = Depends(get_db)):
    await verify_csrf(request)
    require_member(request, db)
    rate_limiter.check(client_key(request, "analyze"), 60, 60)
    listing = db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status_code=404)
    payload = await request.json()
    try:
        values = {
            name: Decimal(str(payload.get(name, 0)))
            for name in ("acquisition_cost", "market_value", "repairs", "other_costs")
        }
        if any(value > Decimal("1000000000") for value in values.values()):
            raise ValueError("Value is too large")
        return rescore_listing(listing, **values)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _background_refresh(source: str) -> None:
    with SessionLocal() as db:
        if source == "all":
            refresh_all(db, trigger="manual")
        else:
            refresh_source(db, source, trigger="manual")


@app.post("/api/refresh", status_code=202)
async def manual_refresh(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    await verify_csrf(request)
    user = require_member(request, db)
    rate_limiter.check(f"refresh:{user.id}", 3, 300)
    payload = await request.json()
    source = str(payload.get("source", "all"))[:64]
    if source != "all" and source not in SOURCE_BY_SLUG:
        raise HTTPException(status_code=422, detail="Unknown source")
    background_tasks.add_task(_background_refresh, source)
    return {"status": "queued", "source": source}


@app.get("/sources", response_class=HTMLResponse)
def sources_page(request: Request, db: Session = Depends(get_db)):
    require_user(request, db)
    sources = list(db.scalars(select(SourceStatus).order_by(SourceStatus.name)))
    runs = list(db.scalars(select(RefreshRun).order_by(desc(RefreshRun.started_at)).limit(20)))
    return templates.TemplateResponse(
        request,
        "sources.html",
        page_context(request, db, active_page="sources", sources=sources, runs=runs),
    )


@app.get("/billing", response_class=HTMLResponse)
def billing_page(request: Request, db: Session = Depends(get_db)):
    require_user(request, db)
    return templates.TemplateResponse(
        request,
        "billing.html",
        page_context(
            request,
            db,
            active_page="billing",
            stripe_configured=bool(settings.stripe_secret_key and settings.stripe_price_id),
            checkout=request.query_params.get("checkout", ""),
        ),
    )


@app.post("/billing/checkout")
async def checkout(request: Request, db: Session = Depends(get_db)):
    await verify_csrf(request)
    user = require_user(request, db)
    rate_limiter.check(f"checkout:{user.id}", 5, 300)
    try:
        url = billing.create_checkout_url(user)
    except billing.BillingNotConfigured as exc:
        return templates.TemplateResponse(
            request,
            "billing.html",
            page_context(request, db, active_page="billing", stripe_configured=False, error=str(exc)),
            status_code=503,
        )
    return RedirectResponse(url, status_code=303)


@app.post("/billing/portal")
async def billing_portal(request: Request, db: Session = Depends(get_db)):
    await verify_csrf(request)
    user = require_user(request, db)
    try:
        url = billing.create_portal_url(user)
    except billing.BillingNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RedirectResponse(url, status_code=303)


@app.post("/billing/demo-activate")
async def demo_activate(request: Request, db: Session = Depends(get_db)):
    await verify_csrf(request)
    user = require_user(request, db)
    if settings.app_env == "production" or not settings.billing_bypass:
        raise HTTPException(status_code=404)
    user.subscription_status = "active"
    db.commit()
    return RedirectResponse("/app", status_code=303)


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    if len(payload) > 1_000_000:
        raise HTTPException(status_code=413)
    signature = request.headers.get("stripe-signature", "")
    try:
        event = billing.construct_webhook(payload, signature)
        processed = billing.process_event(db, event)
    except billing.BillingNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook") from exc
    return {"received": True, "processed": processed}


def _contact_context(request: Request, db: Session, **values) -> dict:
    user = current_user(request, db)
    context = {
        "topics": contact.TOPICS,
        "contact_enabled": settings.contact_form_enabled,
        "max_message": contact.MAX_MESSAGE,
        "sent": False,
        "error": "",
        # A fresh challenge per render: the browser solves it when the visitor
        # ticks the box, which is what unlocks the submit button.
        "challenge": challenge.issue(get_csrf_token(request)),
        "pow_bits": settings.contact_pow_bits,
        # Prefilled for a signed-in member; a rejected post overrides this with
        # what they actually typed so nothing has to be retyped.
        "form": {
            "email": user.email if user else "",
            "topic": "feedback",
            "name": "",
            "subject": "",
            "message": "",
        },
    }
    context.update(values)
    return page_context(request, db, **context)


@app.get("/contact", response_class=HTMLResponse)
def contact_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "contact.html",
        _contact_context(request, db, sent=request.query_params.get("sent") == "1"),
    )


@app.post("/contact", response_class=HTMLResponse)
async def submit_contact(
    request: Request,
    email: str = Form(""),
    message: str = Form(""),
    topic: str = Form("feedback"),
    name: str = Form(""),
    subject: str = Form(""),
    company: str = Form(""),
    challenge_token: str = Form(""),
    challenge_counter: str = Form(""),
    not_a_robot: str = Form(""),
    db: Session = Depends(get_db),
):
    await verify_csrf(request)
    # A public endpoint that sends mail: cap it hard per client.
    rate_limiter.check(client_key(request, "contact"), 5, 900)

    def reject(error: str, status_code: int = 400):
        return templates.TemplateResponse(
            request,
            "contact.html",
            _contact_context(
                request,
                db,
                sent=False,
                error=error,
                form={
                    "email": email[:320],
                    "topic": topic if topic in contact.TOPICS else "feedback",
                    "name": name[:contact.MAX_NAME],
                    "subject": subject[:contact.MAX_SUBJECT],
                    "message": message[:contact.MAX_MESSAGE],
                },
            ),
            status_code=status_code,
        )

    # Honeypot: a hidden field only an automated submitter fills in. Report
    # success so the bot has nothing to tune against, but send nothing.
    if company.strip():
        logger.info("Contact form honeypot triggered; submission dropped")
        return RedirectResponse("/contact?sent=1", status_code=303)

    if not settings.contact_form_enabled:
        return reject(
            "The contact form is not configured yet. Email us directly and we will pick it up.",
            status_code=503,
        )

    # Bot gate, before any validation work: the challenge is signed and timed,
    # so a script that never loaded the form cannot produce a valid one.
    if not not_a_robot:
        return reject("Tick the verification box so we know you are a person.")
    try:
        challenge.verify(challenge_token, challenge_counter, get_csrf_token(request))
    except challenge.ChallengeError as exc:
        logger.info("Contact challenge rejected (%s)", type(exc).__name__)
        return reject(str(exc))

    # Only if the operator set CONTACT_DAILY_LIMIT; off by default.
    budget_left = contact.daily_budget_remaining(db)
    if budget_left is not None and budget_left <= 0:
        logger.warning("Contact form daily cap reached; submission refused")
        return reject(
            "We have hit today's message limit. Please try again tomorrow.", status_code=429
        )

    try:
        normalized = validate_email(email, check_deliverability=False).normalized
    except EmailNotValidError:
        return reject("Enter a valid email address so we can reply.")
    body = message.strip()
    if len(body) < contact.MIN_MESSAGE:
        return reject("Tell us a little more so we can act on it.")

    signed_in = current_user(request, db)
    submission = contact.ContactSubmission(
        email=normalized,
        message=body[: contact.MAX_MESSAGE],
        topic=topic if topic in contact.TOPICS else "other",
        name=" ".join(name.split())[: contact.MAX_NAME],
        subject=subject[: contact.MAX_SUBJECT],
        account_email=signed_in.email if signed_in else "",
        page_url=request.headers.get("referer", "")[:300],
    )
    try:
        await contact.send_contact_message(submission, db)
    except contact.DailyLimitReached:
        logger.warning("Contact form daily cap reached at send time; submission refused")
        return reject(
            "We have hit today's message limit. Please try again tomorrow.", status_code=429
        )
    except Exception as exc:
        logger.warning("Contact form delivery failed (%s)", type(exc).__name__)
        return reject(
            "We could not send that just now. Please try again shortly.", status_code=502
        )
    contact.record_delivery(db, submission, client_key(request, "contact"))
    return RedirectResponse("/contact?sent=1", status_code=303)


@app.get("/legal/{page}", response_class=HTMLResponse)
def legal(page: str, request: Request, db: Session = Depends(get_db)):
    if page not in {"terms", "privacy", "disclaimer"}:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request, "legal.html", page_context(request, db, legal_page=page)
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "dealsig-web"}


@app.get("/readyz")
def readyz(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ready"}
