#!/usr/bin/env bash
#
# RevOS server hardening — Ubuntu 24.04 (Hetzner Cloud). Run as root on a fresh
# box BEFORE installing Docker. It creates a non-root sudo user with your SSH
# key, locks down SSH (key-only, NO root login), and enables a firewall +
# fail2ban + automatic security updates, network sysctl hardening, swap, and
# time sync.
#
# Usage (as root):
#   ./harden.sh <username> "<your-ssh-public-key>"
# e.g.
#   ./harden.sh deploy "ssh-ed25519 AAAA... you@laptop"
#
# Prefer to keep root SSH login? Use ./harden-keeproot.sh instead.
#
# After it finishes, open a NEW terminal and confirm `ssh <username>@<ip>` works
# and that you can `sudo` — THEN close the root session. Root SSH + password
# auth are disabled, so verify key login first. A reload does not drop your
# current session, and the Hetzner web console is always a fallback.

set -euo pipefail

NEW_USER="${1:?usage: harden.sh <username> \"<ssh-public-key>\"}"
SSH_KEY="${2:?provide your SSH public key as the second argument}"

if [[ $EUID -ne 0 ]]; then echo "Run as root." >&2; exit 1; fi
echo ">> Hardening for user '$NEW_USER' ..."

# 1. Non-root sudo user with your SSH key -----------------------------------
id "$NEW_USER" &>/dev/null || adduser --disabled-password --gecos "" "$NEW_USER"
usermod -aG sudo "$NEW_USER"
install -d -m 700 -o "$NEW_USER" -g "$NEW_USER" "/home/$NEW_USER/.ssh"
printf '%s\n' "$SSH_KEY" > "/home/$NEW_USER/.ssh/authorized_keys"
chmod 600 "/home/$NEW_USER/.ssh/authorized_keys"
chown "$NEW_USER:$NEW_USER" "/home/$NEW_USER/.ssh/authorized_keys"

# 1b. LOCKOUT GUARD: we are about to disable BOTH root login and password auth,
#     so the new user MUST have a usable key or you'd be locked out. ---------
if [[ ! -s "/home/$NEW_USER/.ssh/authorized_keys" ]]; then
  echo "!! Refusing to lock down SSH: /home/$NEW_USER/.ssh/authorized_keys is empty." >&2
  echo "!! Pass a valid public key as the second argument." >&2
  exit 1
fi

# 2. SSH hardening: key-only, no root -----------------------------------------
#    Our drop-in is named 00- so it is parsed FIRST; sshd is first-match-wins,
#    so our values beat cloud-init's 50-cloud-init.conf ('PasswordAuthentication
#    yes'). We also align that file, then verify the EFFECTIVE config with
#    `sshd -T` (not just `sshd -t`, which is syntax-only).
install -d -m 755 /etc/ssh/sshd_config.d
rm -f /etc/ssh/sshd_config.d/99-revos-hardening.conf   # drop any stale prior-run file
cat > /etc/ssh/sshd_config.d/00-revos-hardening.conf <<EOF
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
PermitEmptyPasswords no
X11Forwarding no
MaxAuthTries 3
LoginGraceTime 30
AllowUsers $NEW_USER
EOF

# Align cloud-init's competing drop-in so it can't override us (now or after a
# cloud-init reboot rewrite).
CI=/etc/ssh/sshd_config.d/50-cloud-init.conf
if [[ -f "$CI" ]]; then
  sed -ri "s/^[[:space:]]*PasswordAuthentication[[:space:]]+.*/PasswordAuthentication no/I" "$CI"
  sed -ri "s/^[[:space:]]*KbdInteractiveAuthentication[[:space:]]+.*/KbdInteractiveAuthentication no/I" "$CI"
  sed -ri "s/^[[:space:]]*PermitRootLogin[[:space:]]+.*/PermitRootLogin no/I" "$CI"
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
if [[ "$(eff passwordauthentication)" != "no" ]]; then
  echo "!! Effective PasswordAuthentication is '$(eff passwordauthentication)', expected 'no' — a drop-in is overriding us. Aborting." >&2
  exit 1
fi
if [[ "$(eff permitrootlogin)" != "no" ]]; then
  echo "!! Effective PermitRootLogin is '$(eff permitrootlogin)', expected 'no'. Aborting." >&2
  exit 1
fi
echo ">> SSH hardened and verified (key-only, root login disabled)."

# 3. Packages: firewall, fail2ban, unattended-upgrades ----------------------
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ufw fail2ban unattended-upgrades

# 4. Host firewall (defense in depth; the Hetzner Cloud Firewall is primary) -
ufw --force reset
ufw allow OpenSSH || true
ufw allow 80/tcp || true
ufw allow 443/tcp || true
ufw allow 443/udp || true          # HTTP/3 (QUIC)
ufw default deny incoming || true
ufw default allow outgoing || true
ufw --force enable || echo "WARN: ufw enable failed; the Hetzner Cloud Firewall is your primary filter." >&2

# 5. fail2ban for SSH brute-force (read the journal; don't abort on start) ----
cat > /etc/fail2ban/jail.d/sshd.local <<EOF
[sshd]
enabled  = true
backend  = systemd
maxretry = 3
findtime = 10m
bantime  = 1h
EOF
systemctl enable fail2ban >/dev/null 2>&1 || true
systemctl restart fail2ban || echo "WARN: fail2ban failed to start; continuing." >&2
systemctl is-active --quiet fail2ban && echo ">> fail2ban active." || echo "WARN: fail2ban not active — check 'journalctl -u fail2ban'." >&2

# 6. Automatic security updates ----------------------------------------------
cat > /etc/apt/apt.conf.d/20auto-upgrades <<EOF
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

# 7. Network / kernel sysctl hardening (-e ignores keys absent on this kernel)
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

# 8. Swap (guarded; clean up a partial file on failure) ----------------------
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

# 9. Time sync (TLS validity / token expiry accuracy) ------------------------
timedatectl set-ntp true 2>/dev/null || true

echo ""
echo ">> Hardening complete. Your current session stays open across the reload."
echo ">> In a NEW terminal, verify:  ssh ${NEW_USER}@<server-ip>  and  sudo -v"
echo ">> Only then close this root session. Root SSH + password auth are now OFF."
