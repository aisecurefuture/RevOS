#!/usr/bin/env bash
#
# RevOS server hardening — Ubuntu 24.04 (Hetzner Cloud). Run as root on a fresh
# box BEFORE installing Docker. It creates a non-root sudo user with your SSH
# key, locks down SSH, enables a firewall + fail2ban + automatic security
# updates, applies network sysctl hardening, adds swap, and syncs the clock.
#
# Usage (as root):
#   ./harden.sh <username> "<your-ssh-public-key>"
# e.g.
#   ./harden.sh deploy "ssh-ed25519 AAAA... you@laptop"
#
# After it finishes, open a NEW terminal and confirm `ssh <username>@<ip>` works
# and that you can `sudo` — THEN close the root session. Root SSH + password
# auth are disabled, so verify key login first.

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

# 2. SSH hardening: key-only, no root, fewer tries --------------------------
cat > /etc/ssh/sshd_config.d/99-revos-hardening.conf <<EOF
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PubkeyAuthentication yes
PermitEmptyPasswords no
X11Forwarding no
MaxAuthTries 3
LoginGraceTime 30
AllowUsers $NEW_USER
EOF
systemctl reload ssh 2>/dev/null || systemctl reload sshd

# 3. Packages: firewall, fail2ban, unattended-upgrades ----------------------
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ufw fail2ban unattended-upgrades

# 4. Host firewall (defense in depth; the Hetzner Cloud Firewall is primary) -
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp        # HTTP/3 (QUIC)
ufw --force enable

# 5. fail2ban for SSH brute-force --------------------------------------------
cat > /etc/fail2ban/jail.d/sshd.local <<EOF
[sshd]
enabled  = true
maxretry = 4
findtime = 10m
bantime  = 1h
EOF
systemctl enable --now fail2ban

# 6. Automatic security updates ----------------------------------------------
cat > /etc/apt/apt.conf.d/20auto-upgrades <<EOF
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

# 7. Network / kernel sysctl hardening ---------------------------------------
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
sysctl --system >/dev/null

# 8. Swap (avoids OOM during image builds / ffmpeg transcodes) ---------------
if ! swapon --show | grep -q '/swapfile'; then
  fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# 9. Time sync (TLS validity / token expiry accuracy) ------------------------
timedatectl set-ntp true 2>/dev/null || true

echo ""
echo ">> Hardening complete."
echo ">> In a NEW terminal, verify:  ssh ${NEW_USER}@<server-ip>  and  sudo -v"
echo ">> Only then close this root session. Root SSH + password auth are now OFF."
