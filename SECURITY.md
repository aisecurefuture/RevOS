# RevOS — Security

RevOS is built **approval-first** and **permission-based**: no outbound message
or AI-generated action reaches a human without an explicit review/approval step,
and marketing email only ever goes to confirmed opt-ins.

## Controls (OWASP Web / LLM / Agentic)

| Area | Control |
|---|---|
| Access control | Role dependency (`viewer<editor<admin<owner`) on every route; deny-by-default; admin-only for sends/approvals/publishing/integrations |
| Auth | bcrypt+SHA-256 password hashing; JWT (typed access/refresh) in HttpOnly cookies; **per-user `token_version`** invalidates all tokens on password change |
| CSRF | Signed double-submit token on every state-changing request |
| Injection | 100% parameterized SQL (no string interpolation); **sandboxed + autoescaped** Jinja (anti-SSTI); fixed-arg subprocess for ffmpeg |
| SSRF | Every server-side outbound fetch passes an allowlist + private-IP/loopback block (anti DNS-rebind) |
| XSS | bleach allowlist on all stored/rendered HTML; no inline `style`; **no `target`** (no reverse-tabnabbing); strict CSP + framing rules |
| Secrets | Env-only; never logged or returned; opaque 500s; production hard-fails on default/insecure config |
| Webhooks | Resend (Svix), Stripe, and Zapier inbound all verify HMAC signatures with **replay protection** before any state change |
| Consent / approval | Send-time enforcement: suppressed addresses and unconfirmed leads are never emailed; bulk sends and sequence steps require human approval |
| OWASP-LLM | Prompt-injection isolation (user input wrapped as data + delimiter stripping); output sanitized; **draft-only** (never auto-executed); rate-limited |
| DoS | Per-IP rate limits (real client IP, not spoofable XFF); global body-size ceiling; upload + video + CSV-row caps |

## Security audit (Module 15)

A multi-agent adversarial review covered 8 dimensions (access control, auth/
session, injection/SSRF, XSS, compliance invariants, webhooks/secrets, LLM/
agentic, DoS), with every candidate finding independently verified. The core
invariants held — **no critical or high findings**. 16 medium/low defense-in-
depth items were confirmed and **all remediated**:

- JWT revocation on password change (`token_version`)
- Production config now fail-closes on default secret / insecure cookies
- `SECRET_KEY` minimum raised to 32 chars
- X-Forwarded-For only trusted behind a configured proxy (`TRUST_PROXY`)
- Rate limits added to public render/redirect, provider webhooks, and inbound
- Global request body-size ceiling + media video-duration cap + CSV row cap
- Content approval is admin-only (aligned with `can_approve`)
- `target=_blank` removed from sanitizer (reverse-tabnabbing)
- Prompt-injection delimiter stripping
- Zapier inbound webhook replay protection (signed timestamp)

Regression tests cover token-version invalidation, production-config hard-fail,
admin-only content approval, the sanitizer hardening, and the webhook
replay/signature checks.

## Reporting

This is a private application. Rotate `SECRET_KEY`, `RESEND_API_KEY`, Stripe and
webhook secrets immediately if a leak is suspected (a `SECRET_KEY` rotation
invalidates all sessions, signed opt-in/unsubscribe links, and CSRF tokens).
