# Deploying RevOS to a Hetzner VPS (revos360.com)

A start-to-finish runbook for a **dedicated** Hetzner Cloud server with Caddy
handling automatic HTTPS. Budget ~30 minutes.

## 1. Provision the server

Create a Hetzner Cloud server:
- **Type:** `CAX21` (Arm, 4 vCPU / 8 GB, ~€7/mo) or `CPX31` (x86, 4 vCPU / 8 GB,
  ~€14/mo). Avoid the 2 GB tiers — Postgres + a video transcode will OOM.
- **Image:** Ubuntu 24.04.
- **SSH key:** add yours so you can log in without a password.
- Note the server's public **IPv4** (and IPv6 if you want AAAA records).

## 2. DNS (point the domains at the server)

At your domain registrar, create these records (replace `203.0.113.10` with your IP):

| Type | Name | Value |
|---|---|---|
| A | `revos360.com` (`@`) | `203.0.113.10` |
| A | `www` | `203.0.113.10` |
| A | `app` | `203.0.113.10` |
| A | `api` | `203.0.113.10` |
| A | `revos365.com` (`@` + `www`) | `203.0.113.10` |
| A | `officialrevos.com` (`@` + `www`) | `203.0.113.10` |

Wait for DNS to propagate (`dig +short app.revos360.com` should return your IP)
before bringing Caddy up — it needs the records resolvable to issue certificates.

## 3. Harden the server

SSH into the fresh box **as root**, then run the bundled hardening script. It
creates a non-root sudo user with your SSH key, locks down SSH (key-only, no
root login), and enables a firewall, fail2ban, automatic security updates,
network sysctl hardening, swap, and time sync.

```bash
# Copy harden.sh up (it's in the repo's deploy/ folder), then:
chmod +x harden.sh
./harden.sh deploy "ssh-ed25519 AAAA... you@laptop"   # your username + PUBLIC key
```

What it does:
- **Non-root sudo user** with your key; **disables root SSH + password auth**.
- **`ufw`** allowing only 22 (SSH), 80 (ACME + HTTP→HTTPS), 443 TCP **and** UDP
  (HTTPS + HTTP/3). Postgres 5432 / Redis 6379 stay internal.
- **fail2ban** on SSH, **unattended-upgrades** for security patches.
- **sysctl** hardening (SYN cookies, no redirects/source-routing, `rp_filter`).
- **2 GB swap** (prevents OOM during image builds / ffmpeg transcodes).

> ⚠️ Before closing the root session, open a **new** terminal and confirm
> `ssh deploy@<ip>` works and `sudo -v` succeeds — root login is now disabled.

**Prefer to keep root SSH login?** Use the alternative
[`harden-keeproot.sh`](harden-keeproot.sh) instead — same baseline, but it keeps
root reachable over SSH (key-only by default) and does **not** create a separate
user:

```bash
./harden-keeproot.sh "ssh-ed25519 AAAA... you@laptop"   # ensures a root key, then hardens
```

It verifies the **effective** SSH config with `sshd -T` after reload — catching
the cloud-init drop-in that otherwise silently keeps password auth on — and
refuses to disable password auth unless a usable root key is present, so it
can't quietly fail or lock you out.

**Also add a Hetzner Cloud Firewall** (in the Cloud console) allowing only
inbound 22/80/443. This sits *in front of* the VM and is the authoritative
network filter — see the Docker note below for why that matters.

## 4. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker deploy && newgrp docker     # run docker without sudo
```

> **Docker + `ufw` caveat:** Docker inserts its own iptables rules for
> *published* ports, bypassing `ufw`. RevOS's prod compose **does not publish**
> Postgres/Redis (`ports: []`) — only Caddy publishes 80/443 — so nothing is
> exposed. Keep it that way, and rely on the **Hetzner Cloud Firewall** as the
> authoritative edge filter (Docker can't bypass it).

## 5. Get the code + configure

```bash
git clone <your-repo-url> revos && cd revos     # or scp the project up
cp .env.prod.example .env
# Generate a strong secret and a DB password:
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(64))"
# Edit .env: paste SECRET_KEY, set OWNER_PASSWORD, POSTGRES_PASSWORD (and the
# matching DATABASE_URL), and any RESEND_/STRIPE_/AI keys you have.
nano .env
# Set your real ACME email in the Caddyfile:
nano Caddyfile        # change hello@revos360.com if you like
```

## 6. Launch

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

This builds the images, runs migrations (the one-shot `migrate` service), starts
api/worker/beat/frontend/db/redis/backup, and brings up Caddy. **Caddy obtains
Let's Encrypt certificates for all four domains automatically on first request
and renews them on its own — there is no certbot to install or cron to manage.**

Watch it come up:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f caddy api
```

## 7. Seed your data + first login

```bash
# Seed owner + 5 brands + Hao campaign (idempotent):
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api python -m app.seed.seed

# Optional: import your LinkedIn contacts (as CRM contacts, NOT a mail list).
# Copy the CSV onto the server, then:
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec \
  -e SEED_LINKEDIN_CSV=/app/Connections.csv api python -m app.seed.seed
```

Then open **https://app.revos360.com** and sign in with `OWNER_EMAIL` /
`OWNER_PASSWORD`. The marketing site is live at **https://revos360.com**.

## 8. Verify

```bash
curl -s https://api.revos360.com/health/ready        # {"status":"ok","database":true,...}
curl -sI https://revos360.com | grep -i strict-trans  # HSTS present
curl -sI https://app.revos360.com                     # 200 from the console
```

## 9. Email (Resend)

1. Add your sending domain(s) in Resend and verify DNS (SPF/DKIM). For the RevOS
   brand, use `mail.revos360.com` to keep the root's reputation isolated.
2. Add a `SenderIdentity` per brand in the app (each business sends as itself).
3. Set `RESEND_API_KEY`, flip `EMAIL_TEST_MODE=false`, add the webhook
   `https://api.revos360.com/api/webhooks/resend` with `RESEND_WEBHOOK_SECRET`,
   then `docker compose ... up -d` to apply.

## 10. Backups

The `backup` service writes a gzipped `pg_dump` to `./backups/` nightly (7-day
retention). **Sync these off the box** — a server-local backup won't survive a
server loss. Easiest: a Hetzner Storage Box + a daily `rclone`/`scp` of
`./backups`, or set `STORAGE_BACKEND=s3` and also push dumps to object storage.

Restore:
```bash
gunzip -c backups/revos_YYYY-MM-DD_HHMMSS.sql.gz | \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T db \
  psql -U revos -d revos
```

## 11. Updating

```bash
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
# migrations run automatically via the one-shot migrate service.
```

---

### Other platforms

The same image runs on **Render / Railway / Fly.io / DigitalOcean App Platform /
AWS Lightsail**. Use the platform's managed Postgres + Redis, run
`alembic upgrade head` on deploy, deploy `frontend/` as a Next.js app pointing
`BACKEND_INTERNAL_URL` at the API, and let the platform terminate TLS (drop
Caddy). Keep `APP_ENV=production`, `COOKIE_SECURE=true`, `TRUST_PROXY=true`.
