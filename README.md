# RevOS — Revenue Operating System

A modular, **approval-first** marketing & sales automation platform for multiple
brands, books, and offers. Ethical lead generation, email marketing, content
planning, a media pipeline, CRM, funnels, and revenue analytics — with
permission-based compliance and human-in-the-loop controls baked in.

> **Approval-first, not blind automation.** Every outbound message and every
> AI-generated artifact defaults to a draft / human-review state. Marketing
> email only ever reaches confirmed opt-ins. Nothing is scraped.

- **Architecture & design:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **Security controls & audit:** [SECURITY.md](SECURITY.md)
- **Every config var:** [.env.example](.env.example)

---

## What's inside

| Module | Highlights |
|---|---|
| Brands | Multi-brand: voice, audiences, buyer personas, offers, CTAs — adding a brand is pure data |
| Lead capture | Hosted landing pages, embeddable forms, **double opt-in**, UTM capture, anti-spam |
| Email (Resend) | Per-brand sender identity, templates, suppression, **send-time consent enforcement**, status webhooks |
| Sequences | Multi-step nurtures: delays, stop conditions, goals, A/B subjects, **per-step approval** |
| CRM-lite | Contacts, companies, deals, pipeline, notes, tasks, lead scoring, **LinkedIn import** |
| Content | Channel drafts + the Draft→…→Published state machine, pillars/hooks/CTAs, social adapters (draft-safe) |
| Media | Upload → Pillow/ffmpeg **per-platform renditions**, original preserved, approval-gated |
| Analytics | Revenue/leads/funnel/UTM/ROI dashboards, event tracking, CSV export |
| Integrations | Stripe checkout+webhooks, Airtable/Sheets/Notion export, Zapier/Make (HMAC) |
| AI | Provider abstraction (Anthropic/OpenAI/local), **draft-only** with OWASP-LLM guardrails |

**Stack:** FastAPI · SQLModel · PostgreSQL · Alembic · Celery/Redis · Resend ·
Next.js 16 + Tailwind · Docker Compose. **135 backend tests, 0 npm vulnerabilities.**

---

## Quick start (development)

```bash
# 1. Configure
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(64))"   # paste into SECRET_KEY
# set OWNER_EMAIL / OWNER_PASSWORD for your first admin login

# 2. Launch the full stack (api, worker, beat, postgres, redis, frontend)
docker compose up --build

# 3. In another shell: apply migrations and seed the 5 brands + owner
docker compose exec api alembic upgrade head
docker compose exec api python -m app.seed.seed

# 4. Open the admin console and sign in with OWNER_EMAIL / OWNER_PASSWORD
open http://localhost:3000
```

- API docs (dev only): http://localhost:8000/docs
- Health: `GET /health/live`, `GET /health/ready` (DB + integration status)

### Run pieces without Docker

```bash
# Backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(64))")
alembic upgrade head && python -m app.seed.seed
uvicorn app.main:app --reload

# Frontend
cd frontend && npm install && npm run dev
```

---

## Seeding

`python -m app.seed.seed` is **idempotent** and creates:

- the **owner** admin user (from `OWNER_EMAIL` / `OWNER_PASSWORD`)
- the default 9-stage sales pipeline
- the **5 brands** — CyberArmor.ai, TradicoreUSA.com, PatrickMKellyJr.com,
  FirstGoldenLogistics.com, and the *AI Secure Future* book — each with voice,
  audiences, personas, offers, CTAs, pillars, and a consent-first form;
  CyberArmor and the book also get starter email sequences
- the **Hao (@jhhfit) influencer** social campaign with draft posts

**Optional LinkedIn import** — set `SEED_LINKEDIN_CSV` to your `Connections.csv`
path and they import as CRM **contacts** (`source=linkedin_import`). They are
**not** added to any marketing list and are not mailable until they opt in
(CAN-SPAM / GDPR safe). Verified: a 6,460-row export imports ~6,030 contacts +
~5,000 companies, with **zero** leads created.

```bash
SEED_LINKEDIN_CSV=/path/to/Connections.csv python -m app.seed.seed
```

---

## Resend (email) setup

Email runs in **test mode** until configured (messages are recorded, not sent).

1. Create an account at https://resend.com and generate an API key.
2. Verify your sending domain(s) and add a `SenderIdentity` per brand
   (from-name + from-email on a verified domain).
3. Set `RESEND_API_KEY` and `EMAIL_TEST_MODE=false` in `.env`.
4. For delivery/open/click/bounce status, add a webhook to
   `POST /api/webhooks/resend` and set `RESEND_WEBHOOK_SECRET` (the Svix signing
   secret). Bounces and complaints auto-suppress the address.

Until a domain is verified, that brand sends only in test mode. Bulk campaign
sends always require a **human approval** in the Approvals queue first.

---

## API documentation

The full OpenAPI schema is served at `/openapi.json`, with interactive docs at
`/docs` (development only — disabled in production). Key surfaces:

- `POST /api/auth/login` · `/refresh` · `/logout` · `/me` · `/password`
- `/api/brands`, `/api/offers`, `/api/campaigns`, `/api/forms`, `/api/landing-pages`
- `/api/leads`, `/api/contacts` (+ `/import`), `/api/companies`, `/api/deals`
- `/api/emails` (+ `/test`, `/preview`), `/api/email-templates`, `/api/suppressions`
- `/api/campaigns/{id}/email/prepare` → `/api/approvals/{id}/approve` (bulk send)
- `/api/sequences` (steps, enroll, tick, goals), `/api/content`, `/api/social`, `/api/media`
- `/api/analytics/*`, `/api/integrations/*`, `/api/ai/*`
- Public (no auth, rate-limited): `/api/public/forms/{slug}/submit`, `/confirm`,
  `/unsubscribe`, `/p/{slug}`, `/u/{code}`, `/track`

---

## Deployment

The production stack uses **Caddy** as the reverse proxy. Caddy obtains **and
auto-renews** Let's Encrypt TLS certificates on its own (built-in ACME) — there
is no certbot to install or cron to manage. It also serves the static marketing
site and routes the subdomains:

| Hostname | Serves |
|---|---|
| `revos360.com`, `www.revos360.com` | static marketing site (`marketing/`) |
| `app.revos360.com` | the Next.js admin console |
| `api.revos360.com` | public endpoints, webhooks, opt-in/landing links |
| `revos365.com`, `officialrevos.com` | 301-redirect → `revos360.com` |

```bash
# migrate job + 4 uvicorn workers + worker/beat + frontend + Caddy + nightly backup
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api python -m app.seed.seed
```

Edit the ACME email in [Caddyfile](Caddyfile); point DNS at the server and certs
provision on first request. Routing lives in [Caddyfile](Caddyfile); production
env defaults are in [.env.prod.example](.env.prod.example).

**Full VPS runbook (recommended): [deploy/hetzner.md](deploy/hetzner.md)** —
server hardening, DNS, firewall, launch, seed, backups, and restore. A
ready-to-run hardening script is at [deploy/harden.sh](deploy/harden.sh).

**Production checklist**
- `APP_ENV=production`, `DEBUG=false` — the app **fails to boot** on insecure
  config (default secret, `COOKIE_SECURE=false`).
- `SECRET_KEY` ≥ 32 random chars; `COOKIE_SECURE=true`.
- `TRUST_PROXY=true` (so the app trusts Caddy's `X-Forwarded-For` for rate
  limiting — only enable behind a trusted proxy).
- Never publish Postgres/Redis ports (the prod compose keeps them internal);
  set `DATABASE_URL`, `REDIS_URL`, and integration keys via env/secrets.
- Run [deploy/harden.sh](deploy/harden.sh) and add a Hetzner Cloud Firewall
  (allow only 22/80/443) — Docker bypasses host `ufw` for published ports, so a
  network-edge firewall is the authoritative layer.

**Other targets** — the single backend image + Postgres + Redis run on
**Render, Railway, Fly.io, DigitalOcean App Platform, AWS Lightsail, or any
VPS**. Use a managed Postgres + Redis, run `alembic upgrade head` on deploy,
deploy `frontend/` as a Next.js app (or the `output: standalone` image) pointing
`BACKEND_INTERNAL_URL` at the API, and let the platform terminate TLS (drop Caddy).

---

## Tests & quality

```bash
cd backend && pytest            # 135 tests (unit + integration; Resend mocked)
ruff check app tests            # lint + bandit security rules
cd ../frontend && npm run typecheck && npm run build   # 0 vulnerabilities
```

Security: a multi-agent OWASP Web/LLM/Agentic audit found **no critical/high
issues**; 16 medium/low defense-in-depth items were remediated. See
[SECURITY.md](SECURITY.md).
