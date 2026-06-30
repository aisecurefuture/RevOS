# RevOS — Revenue Operating System

**A modular, approval-first marketing & sales automation platform.**

RevOS is a multi-brand revenue operating system that automates *ethical, permission-based*
lead generation, email marketing, content planning, CRM workflows, funnels, and revenue
analytics. Every outbound and AI-generated action defaults to **draft / human-review** —
never blind automation.

---

## 1. Design Principles

| Principle | What it means in RevOS |
|---|---|
| **Approval-first** | AI drafts and bulk campaigns require explicit human approval before send/publish. No "auto-send" path exists by default; it must be deliberately enabled per object. |
| **Permission-based** | Contacts must have a recorded consent event to receive marketing email. Imported (e.g. LinkedIn) contacts get `consent=none` and are *not* mailable until they opt in. |
| **Modular / multi-tenant** | Brands, offers, products, books, lead magnets, landing pages, campaigns, sequences are all data rows — adding a new business requires zero code changes. |
| **Secure by default** | Secrets only via env. Parameterized queries. CSRF, rate limits, RBAC, audit logs, output escaping, SSRF allowlists, OWASP Web/LLM/Agentic controls baked in from day one. |
| **Graceful degradation** | Optional integrations (Resend, Stripe, LinkedIn, Meta, OpenAI/Anthropic, PostHog) are *optional*. Missing keys never crash the app — features fall back to mock/draft/copy-paste mode. |
| **Strong typing** | SQLModel + Pydantic v2 end to end; mypy-clean services. |

---

## 2. Technology Stack & Rationale

| Layer | Choice | Why |
|---|---|---|
| API | **FastAPI** (async) | Typed, fast, auto OpenAPI docs (`/docs`). |
| ORM / models | **SQLModel** (SQLAlchemy 2.0 + Pydantic v2) | One class for DB table + API schema; less drift. |
| Database | **PostgreSQL 16** | JSONB for flexible per-brand config; strong constraints. |
| Migrations | **Alembic** | Reversible, auto-generated from models. |
| Background jobs | **Celery** + **Redis** | Email queueing, sequence ticks, retries, scheduled sends. |
| Beat scheduler | **Celery Beat** | Sequence step cron, re-engagement sweeps, digest jobs. |
| Cache / broker | **Redis** | Celery broker + result backend + rate-limit + idempotency store. |
| Email | **Resend Python SDK** | Per-brand sender identity, transactional + campaign sends. |
| Auth | **JWT (HttpOnly cookie)** + **bcrypt** (passlib) + **RBAC** | Secure admin login; roles: owner / admin / editor / viewer. |
| Frontend | **Next.js 14 (App Router)** + **Tailwind CSS** + **shadcn/ui** | Responsive, mobile-friendly admin dashboard. |
| Charts | **Recharts** | Revenue / funnel / UTM visualizations. |
| Secrets | **pydantic-settings** + `.env` | No hardcoded keys; `.env.example` documents every var. |
| Payments | **Stripe** (checkout links + webhooks) | Stripe-ready; revenue attribution. |
| Storage | **Local fs** + optional **S3-compatible** (boto3) | Lead-magnet files, media assets. |
| Analytics | **Internal event table** + optional Plausible / PostHog / GA | Privacy-friendly first-party tracking. |
| Rate limiting | **slowapi** (Redis-backed) | Per-IP + per-route throttles. |
| Tests | **pytest** + **httpx** + **respx** | Unit + integration; Resend mocked. |
| Containers | **Docker Compose** | api, worker, beat, frontend, postgres, redis, Caddy. |

**Assumption:** SQLModel chosen over bare SQLAlchemy for tighter typing; Celery over RQ/APScheduler
for production-grade retries and beat scheduling. These satisfy the "or" options in the spec.

---

## 3. File Tree

```
RevOS/
├── ARCHITECTURE.md                 # this document
├── README.md                       # setup, deploy, Resend, API docs
├── docker-compose.yml              # dev: api, worker, beat, db, redis, frontend
├── docker-compose.prod.yml         # prod overrides + Caddy + nightly backup
├── Caddyfile                       # reverse proxy + automatic HTTPS
├── marketing/                      # static marketing site (revos360.com)
├── deploy/                         # hetzner.md runbook + harden.sh
├── .env.example                    # every config var documented, no secrets
├── .gitignore
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pyproject.toml              # ruff + mypy + pytest config
│   ├── alembic.ini
│   ├── app/
│   │   ├── main.py                 # FastAPI app factory, middleware, routers
│   │   ├── config.py               # Settings (pydantic-settings)
│   │   ├── database.py             # async engine + session dependency
│   │   ├── deps.py                 # shared deps (current_user, db, rbac)
│   │   │
│   │   ├── core/
│   │   │   ├── security.py         # JWT, bcrypt, CSRF, password policy
│   │   │   ├── rbac.py             # Role enum + permission checks
│   │   │   ├── rate_limit.py       # slowapi limiter
│   │   │   ├── audit.py            # audit-log writer
│   │   │   ├── ssrf.py             # URL allowlist / private-IP guard
│   │   │   ├── sanitize.py         # HTML/XSS sanitization (bleach)
│   │   │   └── exceptions.py       # error handlers, safe error envelopes
│   │   │
│   │   ├── models/                 # SQLModel tables
│   │   │   ├── base.py             # TimestampMixin, UUID PK, soft-delete
│   │   │   ├── user.py             # AdminUser, Role, AuditLog, ApiKey
│   │   │   ├── brand.py            # Brand, BrandVoice, Audience, BuyerPersona
│   │   │   ├── offer.py            # Offer, Product, Book, Service, LeadMagnet
│   │   │   ├── lead.py             # Lead, ConsentRecord, Tag, Segment, UTMCapture
│   │   │   ├── crm.py              # Contact, Company, Deal, PipelineStage, Note, Task
│   │   │   ├── campaign.py         # Campaign, LandingPage, Form, FormSubmission
│   │   │   ├── email.py            # EmailTemplate, EmailMessage, Suppression, SenderIdentity
│   │   │   ├── sequence.py         # Sequence, SequenceStep, Enrollment, StepRun, ABTest
│   │   │   ├── content.py          # ContentItem, ContentCalendar, Pillar, Hook, CTA, Hashtag
│   │   │   ├── social.py           # SocialAccount, SocialPost, SocialCampaign
│   │   │   ├── analytics.py        # Event, UTMLink, ConversionGoal, RevenueRecord
│   │   │   └── approval.py         # ApprovalRequest (generic human-in-the-loop gate)
│   │   │
│   │   ├── schemas/                # request/response Pydantic models (non-table)
│   │   │
│   │   ├── routers/
│   │   │   ├── auth.py             # login, logout, refresh, me, password change
│   │   │   ├── brands.py           # brand + audience + persona CRUD
│   │   │   ├── offers.py           # offer/product/book/service/lead-magnet CRUD
│   │   │   ├── leads.py            # lead list, tag, segment, export
│   │   │   ├── crm.py              # contacts/companies/deals/notes/tasks, CSV import/export
│   │   │   ├── campaigns.py        # campaign + landing page + form CRUD
│   │   │   ├── emails.py           # templates, send, preview, suppression, test mode
│   │   │   ├── sequences.py        # sequence builder, enroll, pause/resume, A/B
│   │   │   ├── content.py          # content calendar, drafts, approval states
│   │   │   ├── social.py           # social adapters, draft generation
│   │   │   ├── analytics.py        # dashboards, ROI, funnel, UTM, CSV export
│   │   │   ├── integrations.py     # Stripe, Sheets, Notion, Zapier, Calendly, etc.
│   │   │   ├── approvals.py        # list/approve/reject pending human-review items
│   │   │   ├── ai.py               # AI draft endpoints (always returns drafts)
│   │   │   ├── webhooks.py         # Stripe + Resend + Zapier inbound (signature-verified)
│   │   │   └── public.py           # hosted landing pages, form submit, unsubscribe, double-opt-in
│   │   │
│   │   ├── services/
│   │   │   ├── email_service.py    # Resend wrapper: send/preview/suppress/test-mode/status
│   │   │   ├── sequence_engine.py  # enrollment, delays, segment rules, stop conditions, goals
│   │   │   ├── content_engine.py   # idea/calendar/draft generation, approval transitions
│   │   │   ├── ai_service.py       # provider abstraction (Anthropic/OpenAI/local) + guardrails
│   │   │   ├── crm_service.py      # lead scoring, pipeline transitions, attribution
│   │   │   ├── analytics_service.py# event ingest + aggregation queries
│   │   │   ├── utm_service.py      # UTM builder, link shortener, capture parsing
│   │   │   ├── storage_service.py  # local + S3 file handling
│   │   │   ├── consent_service.py  # consent capture, double opt-in, suppression checks
│   │   │   ├── approval_service.py # generic approval-request lifecycle
│   │   │   ├── export_service.py   # CSV / Sheets / Notion / Airtable formats
│   │   │   └── social/
│   │   │       ├── base.py         # SocialAdapter protocol (draft-only when no keys)
│   │   │       ├── linkedin.py
│   │   │       ├── meta.py         # Instagram + Facebook Graph
│   │   │       ├── twitter.py
│   │   │       └── youtube.py
│   │   │
│   │   ├── workers/
│   │   │   ├── celery_app.py
│   │   │   ├── tasks.py            # send_email, tick_sequences, run_enrollment_step
│   │   │   └── beat_schedule.py    # periodic: sequence ticks, re-engagement, digests
│   │   │
│   │   ├── templates/email/        # Jinja2, autoescaped
│   │   │   ├── base.html
│   │   │   ├── welcome.html
│   │   │   ├── lead_magnet_delivery.html
│   │   │   ├── double_optin.html
│   │   │   ├── unsubscribe_confirmed.html
│   │   │   ├── cyberarmor_buyer_*.html
│   │   │   └── book_launch_*.html
│   │   │
│   │   └── seed/
│   │       ├── seed.py             # idempotent seeding entrypoint
│   │       ├── brands.py           # 5 brands + audiences + offers + CTAs + sequences
│   │       ├── hao_campaign.py     # influencer social campaign
│   │       └── linkedin_import.py  # Connections.csv -> contacts (consent=none)
│   │
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │
│   └── tests/
│       ├── conftest.py            # test db, client, factories
│       ├── test_auth.py
│       ├── test_rbac.py
│       ├── test_email_service.py  # respx-mocked Resend
│       ├── test_sequence_engine.py
│       ├── test_consent.py
│       ├── test_leads_crm.py
│       ├── test_content_approval.py
│       ├── test_security.py       # XSS, SSRF, authz, rate limit
│       └── test_analytics.py
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.ts
│   └── src/
│       ├── app/
│       │   ├── layout.tsx
│       │   ├── (auth)/login/page.tsx
│       │   └── dashboard/
│       │       ├── layout.tsx                # sidebar + brand selector
│       │       ├── page.tsx                  # revenue overview
│       │       ├── leads/page.tsx
│       │       ├── crm/page.tsx              # pipeline board
│       │       ├── campaigns/page.tsx
│       │       ├── emails/page.tsx
│       │       ├── sequences/page.tsx
│       │       ├── content/page.tsx          # calendar + approval queue
│       │       ├── social/page.tsx
│       │       ├── analytics/page.tsx
│       │       ├── approvals/page.tsx        # human-review inbox
│       │       └── settings/page.tsx
│       ├── components/{ui,dashboard,forms,charts}/
│       └── lib/{api.ts,auth.ts,types.ts}
│
└── landing/                        # standalone example landing page (static export)
    └── cyberarmor-checklist/
```

> Reverse proxy / TLS is handled by **Caddy** (see `Caddyfile`), which also
> serves the `marketing/` site and auto-renews Let's Encrypt certificates.

---

## 4. Data Model (entity overview)

```
Brand 1─┬─* Audience ──* BuyerPersona
        ├─* Offer (polymorphic: Product | Book | Service | LeadMagnet)
        ├─* Campaign ─┬─* LandingPage ──* Form ──* FormSubmission
        │             └─* SocialCampaign ──* SocialPost
        ├─* Sequence ──* SequenceStep        (+ ABTest on subject lines)
        ├─* SenderIdentity                   (per-brand Resend "from")
        ├─* ContentItem (state machine)      (+ Pillar, Hook, CTA, Hashtag libs)
        └─* RevenueGoal

Lead ─┬─* ConsentRecord  (double opt-in lifecycle)
      ├─* UTMCapture
      ├─* Tag / Segment membership
      └─1 Contact (CRM identity)

Contact ─* Company
Contact ─* Deal ──1 PipelineStage
Contact ─* Note / Task / EmailMessage / Enrollment

Enrollment (Lead↔Sequence) ──* StepRun ──> EmailMessage
EmailMessage ──> Suppression check ──> Resend
Event ──> analytics aggregation; RevenueRecord ──> Stripe attribution
ApprovalRequest ──> gates any email-send / publish / AI-apply action
```

**Pipeline stages (seeded):** New lead → Engaged → Qualified → Meeting requested →
Proposal sent → Negotiation → Won / Lost / Nurture.

**Content states:** Draft → Needs review → Approved → Scheduled → Published → Archived.

---

## 5. Security Architecture

### OWASP Web Top 10
| Risk | Control |
|---|---|
| Broken access control | RBAC dependency on every router; object-level ownership checks; deny-by-default. |
| Cryptographic failures | bcrypt password hashing; JWT in HttpOnly+Secure+SameSite cookie; TLS at Caddy (auto Let's Encrypt). |
| Injection | SQLModel/SQLAlchemy parameterized queries only; no raw string SQL; Pydantic input validation. |
| Insecure design | Approval gates, suppression checks, consent enforcement as first-class. |
| Security misconfiguration | Secrets via env; security headers (CSP, HSTS, X-Frame-Options, nosniff); debug off in prod. |
| Vulnerable components | Pinned deps; ruff/pip-audit in CI guidance. |
| Auth failures | Rate-limited login; password policy; lockout/backoff; short-lived access + refresh tokens. |
| Integrity failures | Signed webhooks (Stripe/Resend); CSRF tokens on state-changing form posts. |
| Logging failures | Audit log for every privileged/admin action; no secrets in logs. |
| SSRF | URL allowlist + private-IP/loopback block before any server-side fetch (link preview, webhooks). |

### OWASP LLM Top 10
Prompt-injection isolation (user content never trusted as instructions), output encoding,
human-in-the-loop on all AI-applied actions, no secrets in prompts, output never auto-executed,
token/cost rate limits, model/provider allowlist, PII minimization in prompts, draft-only default.

### OWASP Agentic AI
No autonomous send/publish; every agent action produces an `ApprovalRequest`; tool allowlist;
scoped capabilities per role; full audit trail of AI suggestions vs. applied actions; kill-switch
flag per brand to disable all automation.

---

## 6. Modules → Build Order

Per your checkpoint workflow, each numbered module below is one build step. **I stop and ask
you to pick a model after each.**

| # | Module | Key deliverables |
|---|---|---|
| 1 | **Project scaffold + config** | repo layout, Docker Compose, `.env.example`, settings, DB engine, app factory, health check |
| 2 | **Database models + Alembic** | all SQLModel tables, base mixins, initial migration |
| 3 | **Authentication + RBAC + security core** | login/JWT/bcrypt, roles, CSRF, rate limit, audit, headers, SSRF/XSS guards |
| 4 | **Admin dashboard shell** | Next.js app, login, sidebar, brand selector, layout, API client |
| 5 | **Brand / offer / campaign CRUD** | routers + UI for brands, audiences, personas, offers, campaigns |
| 6 | **Lead capture system** | hosted pages, embeddable forms, consent + double opt-in, UTM capture, tagging |
| 7 | **Resend email service** | SDK wrapper, templates, per-brand sender, preview, suppression, test mode, approval gate |
| 8 | **Email sequence engine** | builder, delays, segment rules, stop conditions, goals, pause/resume, A/B subjects |
| 9 | **CRM-lite** | contacts/companies/deals/notes/tasks, pipeline board, lead scoring, CSV import/export, **LinkedIn seed import** |
| 10 | **Content engine + calendar** | idea/draft generation, calendar, pillars/hooks/CTAs/hashtags, approval states, social adapters |
| 11 | **Media pipeline** | upload image/video, **preserve immutable original**, AI enhance/optimize, generate per-platform renditions (IG/TikTok/YT/X aspect ratios), approval-first before posting |
| 12 | **Analytics / revenue intelligence** | dashboards, leads-by-source/brand, ROI, funnel, UTM, revenue-by-offer, CSV export |
| 13 | **Optional integrations** | Stripe, Sheets/Notion/Airtable, Zapier/Make webhooks, Calendly, Plausible/PostHog/GA, UTM/Bitly |
| 14 | **AI strategy layer** | provider abstraction + guardrails (draft-only) wired into emails/content/media/next-best-action |
| 15 | **Tests + security validation** | unit + integration (mocked Resend), security tests, remediation pass |
| 16 | **README + deployment guide + seed data** | full docs, Resend setup, API docs, 5 brands + Hao campaign + example sequences/landing/calendar |

### Media pipeline (Module 11) — design

Lets you upload an image or video and get back platform-ready, AI-optimized
renditions while the original is never modified.

- **Models:** `MediaAsset` (immutable original: kind, path, mime, dimensions,
  duration, checksum, status) and `MediaVariant` (one per platform/aspect: path,
  spec, format, `is_ai_enhanced`, enhancement log, approval state). The original
  file is write-once; every transformation produces a *new* file.
- **Processing (Celery):** deterministic transforms via **Pillow** (images) and
  **ffmpeg** (video) — resize/smart-crop to platform aspect ratios (IG feed 1:1
  & 4:5, IG/TikTok/YT-Short story/reel 9:16, YouTube 16:9, X 16:9), transcode,
  and compress/optimize. A platform-spec table drives target dimensions/bitrate.
- **AI enhance (optional):** routed through the AI service abstraction (Module
  14) for upscaling, auto color/levels, caption/alt-text generation, and
  smart-crop focus suggestions. Degrades gracefully — with no AI keys (or no
  ffmpeg), it still produces deterministic renditions and copy-paste drafts.
- **Approval-first:** variants land in `draft`/`needs_review`; a human approves
  before a variant can be attached to a `SocialPost` for scheduling/posting.
  Nothing is auto-posted.

---

## 7. Assumptions (documented, no questions asked)

1. **SQLModel + Celery** chosen from the allowed "or" options for tightest typing and prod-grade jobs.
2. **Next.js admin** chosen over HTMX for a richer dashboard; it talks to the FastAPI JSON API.
3. **LinkedIn contacts are imported as CRM contacts with `consent=none`** — they are searchable
   and usable for 1:1 sales outreach tracking, but are **not** added to any marketing email list
   and **cannot** be bulk-emailed until they explicitly opt in. This keeps you CAN-SPAM/GDPR-safe.
4. **One Resend account, multiple verified domains** — each brand maps to a `SenderIdentity`
   (from-name + from-email on a verified domain). Until a domain is verified, that brand sends
   only in test mode.
5. **All AI + bulk-send actions are draft/approval-gated by default.** "Auto" modes exist only as
   explicit per-object opt-in flags, off by default.
6. **Hao (@jhhfit)** is modeled as a `Brand` of type `influencer` with a seeded `SocialCampaign`
   across TikTok/YouTube/Instagram/Facebook — draft content only, no platform scraping.
7. **Single-owner deployment** initially (you as `owner`); additional admins/editors/viewers can be
   added through RBAC.

---

## 8. Deployment

- **Dev:** `docker compose up` → api:8000, frontend:3000, postgres:5432, redis:6379.
- **Migrations:** `alembic upgrade head`; **seed:** `python -m app.seed.seed`.
- **Prod targets:** Render / Railway / Fly.io / DigitalOcean / Lightsail / VPS via
  `docker-compose.prod.yml` + Caddy (automatic TLS, security headers) + nightly
  Postgres backup. Server hardening + runbook in `deploy/`. All secrets via env.
