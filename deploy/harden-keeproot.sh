#!/usr/bin/env bash
#
# RevOS server hardening — ROOT-PRESERVING variant (Ubuntu 24.04 / Hetzner).
#
# Same baseline as harden.sh, but it KEEPS root SSH login instead of disabling
# it. Root stays reachable over SSH; by default it is key-only
# (PermitRootLogin=prohibit-password), so you can always get in with the key
# Hetzner provisioned while password brute-force against root is still blocked.
# It does NOT create or require a separate sudo user.
#
# Run as root on the box:
#   ./harden-keeproot.sh                        # harden; keep root key login
#   ./harden-keeproot.sh "ssh-ed25519 AAAA..."  # also install/append a root key first
#
# Two knobs (env vars — defaults are the secure choice):
#   PERMIT_ROOT_LOGIN=prohibit-password   # 'yes' also allows root PASSWORD login (not recommended)
#   PASSWORD_AUTH=no                       # 'yes' allows password auth for everyone (not recommended)
#
# Safe by design: it (a) refuses to disable password auth unless a usable key
# exists (specifically for root when root is key-only), (b) neutralizes
# cloud-init's competing sshd drop-in, and (c) verifies the EFFECTIVE sshd
# config with `sshd -T` after reload — so a silent override cannot leave you
# wrongly hardened or locked out. A reload does not drop your current SSH
# session, and the Hetzner web console is always a fallback.

set -euo pipefail

PERMIT_ROOT_LOGIN="${PERMIT_ROOT_LOGIN:-prohibit-password}"
PASSWORD_AUTH="${PASSWORD_AUTH:-no}"
PUBKEY="${1:-}"

if [[ $EUID -ne 0 ]]; then echo "Run as root." >&2; exit 1; fi
echo ">> RevOS hardening (root login preserved: PermitRootLogin=$PERMIT_ROOT_LOGIN, PasswordAuthentication=$PASSWORD_AUTH)"

if [[ "$PERMIT_ROOT_LOGIN" == "yes" && "$PASSWORD_AUTH" == "yes" ]]; then
  echo "!! WARNING: PermitRootLogin=yes AND PasswordAuthentication=yes means root PASSWORD login over the internet — high risk. Prefer the key-only defaults." >&2
fi

# 0. If a public key was passed, ensure it's in root's authorized_keys -------
if [[ -n "$PUBKEY" ]]; then
  install -d -m 700 /root/.ssh
  touch /root/.ssh/authorized_keys
  chmod 600 /root/.ssh/authorized_keys
  grep -qxF "$PUBKEY" /root/.ssh/authorized_keys || printf '%s\n' "$PUBKEY" >> /root/.ssh/authorized_keys
  echo ">> root SSH key ensured."
fi

# 0b. LOCKOUT GUARD: before disabling password auth, confirm a usable key
#     exists — and specifically that ROOT has one when root is key-only,
#     since this script's whole point is to keep root reachable. -------------
if [[ "$PASSWORD_AUTH" == "no" ]]; then
  root_has_key=0; [[ -s /root/.ssh/authorized_keys ]] && root_has_key=1
  any_has_key=$root_has_key
  if [[ $any_has_key -eq 0 ]]; then
    for f in /home/*/.ssh/authorized_keys; do [[ -s "$f" ]] && { any_has_key=1; break; }; done
  fi
  if [[ $any_has_key -eq 0 ]]; then
    echo "!! Refusing to disable password auth: no authorized_keys for root or any user — that would lock you out." >&2
    echo "!! Fix: ./harden-keeproot.sh \"ssh-ed25519 AAAA... you@host\"   or   PASSWORD_AUTH=yes ./harden-keeproot.sh" >&2
    exit 1
  fi
  if [[ "$PERMIT_ROOT_LOGIN" == "prohibit-password" && $root_has_key -eq 0 ]]; then
    echo "!! PasswordAuthentication=no + PermitRootLogin=prohibit-password, but ROOT has no key in /root/.ssh/authorized_keys." >&2
    echo "!! That locks root out of SSH. Pass a root key as arg 1, or set PERMIT_ROOT_LOGIN=yes / PASSWORD_AUTH=yes." >&2
    exit 1
  fi
fi

# 1. SSH hardening — KEEP root login (key-based by default) ------------------
#    Our drop-in is named 00- so it is parsed FIRST; sshd is first-match-wins,
#    so our values beat cloud-init's 50-cloud-init.conf (which ships
#    'PasswordAuthentication yes'). We also align that file, then verify the
#    EFFECTIVE config with `sshd -T` (not just `sshd -t`, which is syntax-only).
install -d -m 755 /etc/ssh/sshd_config.d
rm -f /etc/ssh/sshd_config.d/99-revos-hardening.conf   # drop any stale prior-run file
cat > /etc/ssh/sshd_config.d/00-revos-hardening.conf <<EOF
PermitRootLogin $PERMIT_ROOT_LOGIN
PasswordAuthentication $PASSWORD_AUTH
KbdInteractiveAuthentication $PASSWORD_AUTH
PubkeyAuthentication yes
PermitEmptyPasswords no
X11Forwarding no
MaxAuthTries 3
LoginGraceTime 30
EOF

# Align cloud-init's competing drop-in so a direct reader isn't misled and a
# cloud-init reboot rewrite can't diverge from our intent.
CI=/etc/ssh/sshd_config.d/50-cloud-init.conf
if [[ -f "$CI" ]]; then
  sed -ri "s/^[[:space:]]*PasswordAuthentication[[:space:]]+.*/PasswordAuthentication $PASSWORD_AUTH/I" "$CI"
  sed -ri "s/^[[:space:]]*KbdInteractiveAuthentication[[:space:]]+.*/KbdInteractiveAuthentication $PASSWORD_AUTH/I" "$CI"
  sed -ri "s/^[[:space:]]*PermitRootLogin[[:space:]]+.*/PermitRootLogin $PERMIT_ROOT_LOGIN/I" "$CI"
fi

# Validate syntax; revert our drop-in if the config won't parse.
if ! sshd -t 2>/tmp/sshd_test.err; then
  echo "!! sshd config test failed — reverting the hardening drop-in:" >&2
  cat /tmp/sshd_test.err >&2
  rm -f /etc/ssh/sshd_config.d/00-revos-hardening.conf
  exit 1
fi
systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || service ssh reload

# Assert the EFFECTIVE values (resolves precedence across ALL drop-ins).
eff() { sshd -T 2>/dev/null | awk -v k="$1" 'tolower($1)==k{print tolower($2)}'; }
want_pw=$([[ "$PASSWORD_AUTH" == "no" ]] && echo no || echo yes)
want_prl=$(printf '%s' "$PERMIT_ROOT_LOGIN" | tr '[:upper:]' '[:lower:]')
if [[ "$(eff passwordauthentication)" != "$want_pw" ]]; then
  echo "!! Effective PasswordAuthentication is '$(eff passwordauthentication)', expected '$want_pw' — another drop-in is overriding us. Aborting." >&2
  exit 1
fi
if [[ "$(eff permitrootlogin)" != "$want_prl" ]]; then
  echo "!! Effective PermitRootLogin is '$(eff permitrootlogin)', expected '$want_prl'. Aborting." >&2
  exit 1
fi
echo ">> SSH hardened and verified (root login retained; effective PasswordAuthentication=$want_pw)."

# 2. Packages: firewall, fail2ban, unattended-upgrades ----------------------
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ufw fail2ban unattended-upgrades

# 3. Host firewall (allow SSH BEFORE enabling; tolerate benign hiccups) ------
ufw allow OpenSSH || true
ufw allow 80/tcp || true
ufw allow 443/tcp || true
ufw allow 443/udp || true   # HTTP/3 (QUIC)
ufw default deny incoming || true
ufw default allow outgoing || true
ufw --force enable || echo "WARN: ufw enable failed; the Hetzner Cloud Firewall is your primary filter." >&2

# 4. fail2ban for SSH brute-force (read the journal; don't abort on start) ---
cat > /etc/fail2ban/jail.d/sshd.local <<EOF
[sshd]
enabled  = true
backend  = systemd
maxretry = 4
findtime = 10m
bantime  = 1h
EOF
systemctl enable fail2ban >/dev/null 2>&1 || true
systemctl restart fail2ban || echo "WARN: fail2ban failed to start; continuing." >&2
systemctl is-active --quiet fail2ban && echo ">> fail2ban active." || echo "WARN: fail2ban not active — check 'journalctl -u fail2ban'." >&2

# 5. Automatic security updates ----------------------------------------------
cat > /etc/apt/apt.conf.d/20auto-upgrades <<EOF
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

# 6. Network / kernel sysctl hardening (-e ignores keys absent on this kernel)
cat > /etc/sysctl.d/99-revos-hardening.conf <<EOF
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.all.rp_filter = 1
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv6.conf.all.accept_redirects = 0
kernel.kptr_restrict = 2
fs.protected_hardlinks = 1
fs.protected_symlinks = 1
EOF
sysctl --system -e >/dev/null || true

# 7. Swap (guarded; clean up a partial file on failure) ----------------------
if ! swapon --show | grep -q '/swapfile'; then
  if fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048 2>/dev/null; then
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
    grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  else
    echo "WARN: swapfile allocation failed; skipping swap." >&2
    rm -f /swapfile
  fi
fi

# 8. Time sync (TLS validity / token expiry accuracy) ------------------------
timedatectl set-ntp true 2>/dev/null || true

echo ""
echo ">> Hardening complete. Root SSH login is PRESERVED (PermitRootLogin=$PERMIT_ROOT_LOGIN)."
echo ">> Your current session stays open across the reload. Verify in a NEW terminal:  ssh root@<server-ip>"
if [[ "$PASSWORD_AUTH" == "no" ]]; then
  echo ">> Password auth is OFF (key-only). The Hetzner web console is your fallback."
fi
