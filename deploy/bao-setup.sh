#!/usr/bin/env bash
# deploy/bao-setup.sh
#
# One-time OpenBao initialisation helper.
# Requires: curl and python3 on the host, docker compose.
#
# Usage:
#   cd /path/to/RevOS
#   docker compose up -d openbao
#   bash deploy/bao-setup.sh

set -euo pipefail

BAO_HOST_ADDR="http://127.0.0.1:8200"
COMPOSE_SERVICE="openbao"

bao_exec() {
    docker compose exec \
        -e "BAO_ADDR=${BAO_HOST_ADDR}" \
        -e "VAULT_ADDR=${BAO_HOST_ADDR}" \
        "${COMPOSE_SERVICE}" bao "$@"
}

echo "==> Waiting for OpenBao HTTP on ${BAO_HOST_ADDR} ..."
for i in $(seq 1 20); do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        --connect-timeout 2 \
        "${BAO_HOST_ADDR}/v1/sys/health" 2>/dev/null || echo "000")
    if [ "${HTTP_CODE}" != "000" ]; then
        echo "    OpenBao responding (HTTP ${HTTP_CODE})."
        break
    fi
    echo "    Attempt ${i}/20 — waiting 3 s ..."
    sleep 3
    if [ "${i}" -eq 20 ]; then
        echo "ERROR: OpenBao did not respond. Check: docker compose logs openbao"
        exit 1
    fi
done

# ------------------------------------------------------------------
# Check current state via the health endpoint (no auth required)
# ------------------------------------------------------------------
HEALTH=$(curl -s "${BAO_HOST_ADDR}/v1/sys/health" 2>/dev/null)
INITIALIZED=$(printf '%s' "${HEALTH}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('initialized','false'))" 2>/dev/null || echo "false")
SEALED=$(printf '%s' "${HEALTH}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('sealed','true'))" 2>/dev/null || echo "true")

echo "    initialized=${INITIALIZED}  sealed=${SEALED}"

if [ "${INITIALIZED}" = "True" ] && [ "${SEALED}" = "False" ]; then
    echo "==> OpenBao is already initialized and unsealed — nothing to do."
    exit 0
fi

if [ "${INITIALIZED}" = "True" ] && [ "${SEALED}" = "True" ]; then
    echo "ERROR: OpenBao is initialized but still sealed."
    echo "  You need the unseal key from the original init run."
    echo "  If you have it, run:"
    echo "    docker compose exec openbao bao operator unseal <KEY>"
    echo "  If the key is lost, wipe the data and re-run this script:"
    echo "    docker compose stop openbao"
    echo "    rm -rf data/openbao/*"
    echo "    docker compose up -d openbao && sleep 5 && bash deploy/bao-setup.sh"
    exit 1
fi

# ------------------------------------------------------------------
# Initialize
# ------------------------------------------------------------------
echo "==> Initializing OpenBao (1 key share, threshold 1) ..."
INIT_OUTPUT=$(bao_exec operator init \
    -key-shares=1 \
    -key-threshold=1 \
    -format=json 2>&1)

echo "    Raw init output (keep this safe):"
printf '%s\n' "${INIT_OUTPUT}"
echo ""

UNSEAL_KEY=$(printf '%s' "${INIT_OUTPUT}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d['unseal_keys_b64'][0])
" 2>/dev/null || true)

ROOT_TOKEN=$(printf '%s' "${INIT_OUTPUT}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d['root_token'])
" 2>/dev/null || true)

if [ -z "${UNSEAL_KEY}" ] || [ -z "${ROOT_TOKEN}" ]; then
    echo "ERROR: Could not parse init output (see raw output above)."
    exit 1
fi

# ------------------------------------------------------------------
# Unseal
# ------------------------------------------------------------------
echo "==> Unsealing OpenBao ..."
bao_exec operator unseal "${UNSEAL_KEY}"

# ------------------------------------------------------------------
# Enable KV v2
# ------------------------------------------------------------------
echo "==> Enabling KV v2 secrets engine at 'secret/' ..."
docker compose exec \
    -e "BAO_ADDR=${BAO_HOST_ADDR}" \
    -e "VAULT_ADDR=${BAO_HOST_ADDR}" \
    -e "BAO_TOKEN=${ROOT_TOKEN}" \
    -e "VAULT_TOKEN=${ROOT_TOKEN}" \
    "${COMPOSE_SERVICE}" bao secrets enable \
        -version=2 \
        -path=secret \
        kv || echo "    (KV engine may already be enabled — continuing)"

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
echo ""
echo "============================================================"
echo "  OpenBao initialization complete!"
echo "============================================================"
echo ""
echo "  Unseal key (SAVE THIS — needed after every restart):"
echo "    ${UNSEAL_KEY}"
echo ""
echo "  Root token:"
echo "    ${ROOT_TOKEN}"
echo ""
echo "  Add to /root/RevOS/.env on this server:"
echo "    BAO_TOKEN=${ROOT_TOKEN}"
echo ""
echo "  Then restart api/worker/beat:"
echo "    docker compose up -d api worker beat"
echo ""
echo "  After any OpenBao restart, unseal with:"
echo "    docker compose exec openbao bao operator unseal ${UNSEAL_KEY}"
echo "============================================================"
