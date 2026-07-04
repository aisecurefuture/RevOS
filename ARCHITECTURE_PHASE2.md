# RevOS Phase 2 — Multi-Tenant SaaS Architecture

Phase 2 turns RevOS from a single-owner internal tool into a public,
multi-tenant SaaS: self-signup, personal + team workspaces, Stripe subscription
billing with a paywall, OpenBao-backed secret custody, and per-account social
account connections for approval-first posting.

**Decisions locked (2026-07-03):**
- **Tenancy:** Hybrid — every user has a personal workspace and can create/join teams.
- **Pricing:** Trial → Pro → Agency → Enterprise (Enterprise = contact-sales).
- **Social build order:** Meta (FB/IG) → YouTube/TikTok → X → LinkedIn.
- **Secrets:** OpenBao (KV v2), tokens never in Postgres.

Phase 1 invariants still hold: **approval-first** (no auto-posting), permission-based,
official APIs only, secrets via env/secret-store, production config fails closed.

---

## 1. Tenancy model (the foundation everything else scopes to)

**Account** is the unit of data isolation and the billing boundary. Every
domain row (brand, contact, campaign, deal, media, connection, …) gains a
non-null `account_id` FK.

- `Account(id, type: personal|team, name, slug, owner_user_id, created_at)`
- `AdminUser` becomes a **global identity** that can belong to many accounts.
- `Membership(user_id, account_id, role)` — role is **per account**
  (`owner > admin > editor > viewer`). The existing RBAC ladder moves here.
- `type=personal` accounts are auto-created on signup (one member, the user);
  `type=team` accounts are user-created and can invite members.

**Active-account context.** A user acts "inside" one account at a time. The
access JWT carries `act` (active account_id); switching accounts re-mints the
token after re-verifying membership. A single dependency resolves
`(user, active_account, role)` and **every** query filters by
`account_id == active_account`. Cross-tenant reads/writes are impossible by
construction, not by discipline.

- `deps.CurrentContext` → `{user, account, role}`; raises 403 on non-membership.
- A SQLAlchemy scoping helper / mixin enforces `account_id` on read + write.
- **Isolation tests are a first-class deliverable**: for every resource, a test
  proves account A cannot read/list/mutate account B's rows (expect 404/403).

**Migration of existing data.** The seeded owner keeps everything: a one-time
Alembic data migration creates the owner's personal Account and stamps all
current brands/contacts/campaigns/etc. with its `account_id`.

---

## 2. Accounts, membership & profiles (P2-M2)

- **Self-signup:** `POST /api/auth/register` (email, password, name) →
  creates `AdminUser` + personal `Account` + `Membership(owner)` →
  emails a verification link (Resend). Rate-limited; abuse controls noted below.
- **Email verification:** `EmailVerification(token, user_id, expires_at)`;
  unverified users can sign in but are gated from billable actions until verified.
- **Profile:** name, avatar, timezone, notification prefs (on `AdminUser` +
  a `UserProfile` row).
- **Teams:** create team account; **invitations** —
  `Invitation(account_id, email, role, token, status, invited_by, expires_at)`
  → invite email → accept (existing user joins; new user signs up then joins).
- **Member management:** list/change roles/remove members; owner transfer.
- **Account switcher** in the UI; last-active account remembered.

---

## 3. Subscriptions & paywall — Stripe Billing (P2-M3)

Subscription lives on the **Account** (both personal and team accounts bill
independently). Stripe is the **source of truth**; our DB mirrors it via webhooks.

- `Account` gains: `stripe_customer_id`, `plan (trial|pro|agency|enterprise)`,
  `subscription_status (trialing|active|past_due|canceled|incomplete)`,
  `trial_ends_at`, `current_period_end`, `seats`.
- **Plans → Stripe Price IDs** are env-configured (`STRIPE_PRICE_PRO`, …) so you
  tune pricing in Stripe without redeploys.
- **Signup starts a 14-day trial** (`trialing`, full Pro-level features).
- **Checkout / management:** Stripe Checkout (subscription mode) to subscribe;
  Stripe **Customer Portal** for upgrades/downgrades/cancel/payment methods.
- **Enterprise** = "contact sales" CTA → lead capture (no self-serve price).
- **Webhooks** (extends the existing `/api/webhooks/stripe`):
  `customer.subscription.created|updated|deleted`, `invoice.paid`,
  `invoice.payment_failed` → update account plan/status.
- **Entitlements & gating.** A `PLAN_LIMITS` map (brands, team seats, social
  connections, monthly AI drafts, sequences on/off, …). A dependency
  `require_entitlement(feature)` / `enforce_limit(resource)` returns **402
  Payment Required** with an upgrade hint when a plan boundary is hit.
- **Post-trial (no free tier):** an expired trial without a paid plan →
  account **locked to billing-only** (read of existing data allowed; create/send/
  post blocked) until they subscribe. Nothing is deleted.

| Tier | For | Rough gating (tune later) |
|---|---|---|
| Trial (14d) | everyone at signup | full Pro features, time-boxed |
| Pro | solo / small | 1 seat, N brands, core + AI + sequences |
| Agency | multi-brand teams | many seats, many brands/connections, higher AI limits |
| Enterprise | large orgs | SSO, custom limits, SLA — contact sales |

---

## 4. OpenBao — secret custody (P2-M4)

Users' social tokens/API secrets are **high-value credentials**; they live in
**OpenBao (KV v2)**, never in Postgres. Postgres stores only non-secret metadata
plus a Bao **path reference**.

- **Service:** `openbao` container on the internal network; app authenticates via
  **AppRole** (`role_id` + `secret_id`), least-privilege policy scoped to the
  app's path prefix. Audit device enabled.
- **Path scheme:** `secret/data/accounts/{account_id}/social/{platform}/{connection_id}`
  holding `{access_token, refresh_token, expires_at, scopes, ...}`.
- **App client:** a thin `secrets_service` (get/put/delete) wrapping the Bao KV
  API over httpx; all social-token reads/writes go through it.
- **Ops reality (flagged for the checkpoint):** OpenBao **seals on restart** — after
  a reboot the app can't read secrets until it's unsealed. Options:
  1. **Auto-unseal** via a transit key / cloud KMS (recommended — survives reboots
     unattended), or
  2. **Manual unseal** on boot (simplest, but a reboot needs a human + unseal keys).
  Unseal keys and the root token are **operator secrets** — stored off-box, never
  in the repo. A `deploy/openbao-init.sh` bootstraps init → unseal → KV engine →
  AppRole → policy; the runbook documents the unseal choice.
- **Envelope-encryption alternative** (AES via a KMS/app key in Postgres) was the
  simpler road not taken; noted in case OpenBao ops prove heavy.

---

## 5. Social connections & OAuth — approval-first posting (P2-M5/M6)

- **Model (metadata only):** `SocialConnection(account_id, platform,
  external_id, handle, display_name, scopes, status, token_ref, connected_by,
  expires_at)`. Connections are **account-scoped** (teammates share the account's
  connected pages) and record who connected them.
- **OAuth flows:** `GET /api/social/{platform}/connect` → provider authorize
  (signed `state` for CSRF) → `GET /api/social/{platform}/callback` exchanges the
  code, writes tokens to **Bao**, metadata to Postgres. Token refresh handled by
  each adapter.
- **Platform adapter abstraction** (mirrors the Phase 1 AI/provider pattern):
  each platform implements `connect / refresh / list_targets / publish`. Built in
  your order: **Meta (FB Pages + IG business) → YouTube / TikTok → X → LinkedIn.**
- **Approval-first (unchanged):** a post → `ApprovalRequest` → on approval the
  adapter publishes via the **official API**. No auto-posting; ties into the
  Phase 1 content/media pipeline (renditions feed platform-specific formats).
- **Real-world gate (set expectations):** live posting needs each platform's
  **developer app approved** (Meta app review + business verification; X paid
  write tier; LinkedIn/TikTok/YouTube review). RevOS builds the full
  connect→store→approve→publish path so a platform goes live the moment its app
  is approved; until then connections work in a sandbox/draft mode.

---

## 6. Settings page — app.revos360.com/settings (P2-M7)

Sections, permission-aware:
- **Profile** (user): name, avatar, timezone, password, notifications.
- **Account & team** (admin+): rename, members, invites, roles, account switcher.
- **Billing** (owner/admin): current plan + usage vs limits, upgrade/downgrade via
  Stripe Customer Portal, invoices, trial countdown.
- **Connections** (editor+): connect/disconnect social accounts, per-brand mapping,
  token status/expiry, reconnect.
- **API & integrations** (admin): the account's own integration keys (Stripe,
  analytics, etc.) — also custodied in OpenBao where secret.

---

## 7. File-tree additions (backend)

```
backend/app/
├── models/            + account.py, membership.py, invitation.py,
│                        subscription.py, social_connection.py, user_profile.py
├── routers/           + accounts.py, members.py, billing.py, social.py, settings.py
│                        (auth.py gains /register, /verify-email)
├── services/          + account_service.py, subscription_service.py,
│                        secrets_service.py (OpenBao), social/*.py (adapters),
│                        entitlements.py
├── deps.py            + CurrentContext (user+account+role), require_entitlement
└── seed/              migration of existing data → owner's personal account
deploy/                + openbao-init.sh ; docker-compose adds `openbao` service
frontend/app/settings/ + profile / team / billing / connections pages
```

---

## 8. Module roadmap (checkpoint after each — switch models freely)

| # | Module | Delivers | Depends on |
|---|---|---|---|
| P2-M1 | **Multi-tenancy foundation** | Account/Membership, active-account context, query scoping, data migration, **cross-tenant isolation tests** | — |
| P2-M2 | **Accounts, members & profiles** | signup + email verify, profiles, teams, invitations, roles, account switch | M1 |
| P2-M3 | **Subscriptions & paywall** | Stripe Billing, plans/prices, checkout + portal, sub webhooks, trial, entitlement gating | M1 |
| P2-M4 | **OpenBao secret custody** | Bao service + init/unseal, AppRole, `secrets_service`, path scheme, runbook | M1 |
| P2-M5 | **Social + OAuth (Meta)** | SocialConnection, OAuth, token→Bao, adapter base, Meta FB/IG, approval-gated publish | M1, M4 |
| P2-M6 | **More platforms** | YouTube/TikTok → X → LinkedIn adapters (phased per app approval) | M5 |
| P2-M7 | **Settings page** | Profile / Team / Billing / Connections / API UI | M2–M6 |
| P2-M8 | **Hardening + docs** | signup abuse controls, tenant-isolation + secret-custody + payments security review, docs | all |

---

## 9. Security & compliance notes

- **Tenant isolation is the #1 risk** — enforced centrally, proven by tests, and
  re-audited in M8. No endpoint trusts a client-supplied `account_id` without a
  membership check.
- **Credential custody** (users' tokens) raises the bar: OpenBao least-privilege,
  audit log, encrypted transit, token refresh + revoke on disconnect, and a clear
  data-handling posture (you're now processing others' PII + access tokens →
  privacy policy / DPA territory; flagged, not legal advice).
- **Payments:** never trust client state; Stripe webhooks are authoritative;
  verify signatures (already in place); handle `past_due`/dunning gracefully.
- **Public signup** widens attack surface: rate limits, email verification, and
  (M8) abuse/bot controls; production still fails closed on insecure config.
