#!/bin/sh
# Auto-unseal watcher for the single-node OpenBao.
#
# OpenBao (file storage, no HSM/transit auto-unseal) seals itself on every
# restart, which silently breaks the whole secrets layer until someone runs
# `bao operator unseal` by hand. This sidecar watches the seal status and
# re-unseals automatically, so deploys and container restarts never take the
# app's secrets offline.
#
# The unseal key comes from BAO_UNSEAL_KEY (set in .env, never committed).
# Since this is a single node whose data lives on the same host, keeping the
# key on that host does not change the threat model — it just removes the
# manual step.

set -u
: "${BAO_ADDR:=http://openbao:8200}"
export BAO_ADDR

log() { echo "bao-unseal: $*"; }

if [ -z "${BAO_UNSEAL_KEY:-}" ]; then
  log "BAO_UNSEAL_KEY is not set — auto-unseal disabled (unseal manually)."
  # Idle instead of crash-looping, so `docker compose up` stays clean in
  # environments that haven't been initialised yet.
  while true; do sleep 3600; done
fi

log "watching ${BAO_ADDR} (checks every 15s)"
while true; do
  status="$(bao status 2>/dev/null || true)"
  if printf '%s' "$status" | grep -qE 'Sealed[[:space:]]+true'; then
    log "OpenBao is sealed — unsealing"
    if bao operator unseal "$BAO_UNSEAL_KEY" >/dev/null 2>&1; then
      log "unsealed OK"
    else
      log "UNSEAL FAILED — check that BAO_UNSEAL_KEY is correct" >&2
    fi
  fi
  sleep 15
done
