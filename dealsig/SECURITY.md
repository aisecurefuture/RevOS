# DealSig AI security policy and launch gate

## Security contact

Report vulnerabilities privately to `security@dealsig.ai`. Do not include sensitive customer data in an initial report. Replace this mailbox with a monitored process and publish response targets before launch.

## MVP threat model

Protected assets are account access, paid features, Stripe subscription state, saved research, source integrity, valuation assumptions, environment credentials, and availability. Primary threats include email-code abuse, identity-provider account collision, passkey/session theft, CSRF, webhook forgery/replay, open redirects, XSS from source content, source-page parser poisoning, SSRF through integration configuration, denial of service via refresh, dependency compromise, database exposure, and fraudulent property payment instructions.

The application renders source text through Jinja auto-escaping, never injects source HTML, permits refresh only for an allowlisted registry, does not follow valuation-provider redirects, verifies Stripe signatures on the raw body, stores webhook IDs for replay protection, and keeps property-money instructions outside DealSig.

## Production launch gate

- [ ] `APP_ENV=production`; demo mode, seed data, and billing bypass disabled.
- [ ] Unique 32+ byte random session secret stored in the VPS secret manager, not `.env` in source control.
- [ ] HTTPS enforced at the proxy; secure cookies and HSTS confirmed in a browser.
- [ ] Database is private, uses a unique strong password, and has encrypted daily backups plus a tested restore.
- [ ] Stripe live keys stored as secrets; webhook signature, replay, cancellation, charge failure, and delayed-payment cases tested.
- [ ] Resend sending domain and sending-only API key verified; email-code throttling, expiration, replay, resend invalidation, and delivery failure tested.
- [ ] Google/Microsoft/Apple redirect URIs, PKCE/state handling, account-collision behavior, passkey recovery, and admin RBAC reviewed.
- [ ] In-memory app rate limiting supplemented by reverse-proxy limits and, if horizontally scaled, a shared Redis limiter.
- [ ] Source licenses/terms/robots policies documented; access-controlled and purpose-limited lists excluded unless permission is obtained.
- [ ] AVM/display/derivative-data license reviewed; provider timeout, quota, spend cap, and outage behavior tested.
- [ ] CSP checked with no violations; external image policy narrowed or images proxied/scanned.
- [ ] Central structured logs and audit events enabled without secrets, passwords, source bodies, or unnecessary personal data.
- [ ] Error/uptime alerts, connector failure alerts, database saturation alerts, and disk/backup alerts routed to an on-call owner.
- [ ] `bash scripts/security-check.sh` passes in CI and container images are scanned before deploy.
- [ ] Legal terms, privacy disclosures, records retention/deletion, incident plan, and Illinois tax-sale wording reviewed by counsel.
- [ ] Independent penetration test completed before handling meaningful production traffic.

## Operational boundaries

Do not add a generic URL fetch endpoint. New source hosts must be code-reviewed and allowlisted. Do not log response bodies from source or payment systems. Do not store card/bank data. Do not accept property deposits, provide wiring instructions copied from unverified email, or claim a DealSig score is an appraisal or guaranteed return.
