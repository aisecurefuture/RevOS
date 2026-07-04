#!/usr/bin/env bash
# deploy/bao-setup.sh
#
# One-time OpenBao initialisation helper.
#
# Run this script ONCE after the very first `docker compose up`.
# OpenBao starts in an uninitialized, sealed state — this script:
#   1. Waits for OpenBao HTTP to be reachable on localhost:8200.
#   2. Initializes it (1-of-1 unseal key).
#   3. Unseals the instance.
#   4. Enables a KV v2 secrets engine at the "secret" mount.
#   5. Prints the root token so you can add it to .env.
#
# Requires: curl (on the host), docker compose
#
# Usage:
#   cd /path/to/RevOS
#   docker compose up -d openbao
#   bash deploy/bao-setup.sh

set -euo pipefail

BAO_HOST_ADDR="http://127.0.0.1:8200"
COMPOSE_SERVICE="openbao"

# Run a bao CLI command inside the container.
bao_exec() {
    docker compose exec \
        -e "BAO_ADDR=http://127.0.0.1:8200" \
        -e "VAULT_ADDR=http://127.0.0.1:8200" \
        "${COMPOSE_SERVICE}" bao "$@"
}

echo "==> Waiting for OpenBao HTTP on ${BAO_HOST_ADDR} ..."

for i in $(seq 1 20); do
    # Health endpoint always returns HTTP even when uninitialized/sealed.
    # curl -s -o /dev/null -w "%{http_code}" exits 0 on any HTTP response.
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
        echo "ERROR: OpenBao did not respond after 60 s."
        echo "  - Is docker compose up? (docker compose ps)"
        echo "  - Check logs: docker compose logs openbao"
        exit 1
    fi
done

echo "==> Checking initialisation state ..."

# bao operator init -status exit codes:
#   0 = initialized + unsealed
#   2 = not initialized  (proceed with init)
#   3 = initialized but sealed
#   1 = error / unreachable
INIT_STATUS=0
bao_exec operator init -status > /dev/null 2>&1 || INIT_STATUS=$?

if [ "${INIT_STATUS}" -eq 0 ]; then
    echo "==> OpenBao is already initialized and unsealed — nothing to do."
    exit 0
fi

if [ "${INIT_STATUS}" -eq 3 ]; then
    echo "ERROR: OpenBao is initialized but sealed."
    echo "  Run: docker compose exec openbao bao operator unseal <key>"
    exit 1
fi

if [ "${INIT_STATUS}" -ne 2 ]; then
    echo "ERROR: Unexpected bao init -status exit code ${INIT_STATUS}."
    echo "  Check: docker compose logs openbao"
    exit 1
fi

echo "==> Initializing OpenBao (1 key share, threshold 1) ..."
INIT_OUTPUT=$(bao_exec operator init \
    -key-shares=1 \
    -key-threshold=1 \
    -format=json)

UNSEAL_KEY=$(printf '%s' "${INIT_OUTPUT}" | grep -o '"unseal_keys_b64":\["[^"]*"' | cut -d'"' -f4)
ROOT_TOKEN=$(printf '%s' "${INIT_OUTPUT}" | grep -o '"root_token":"[^"]*"' | cut -d'"' -f4)

if [ -z "${UNSEAL_KEY}" ] || [ -z "${ROOT_TOKEN}" ]; then
    echo "ERROR: Failed to parse init output. Raw output:"
    printf '%s\n' "${INIT_OUTPUT}"
    exit 1
fi

echo "==> Unsealing OpenBao ..."
bao_exec operator unseal "${UNSEAL_KEY}"

echo "==> Enabling KV v2 secrets engine at 'secret/' ..."
docker compose exec \
    -e "BAO_ADDR=http://127.0.0.1:8200" \
    -e "VAULT_ADDR=http://127.0.0.1:8200" \
    -e "BAO_TOKEN=${ROOT_TOKEN}" \
    -e "VAULT_TOKEN=${ROOT_TOKEN}" \
    "${COMPOSE_SERVICE}" bao secrets enable \
        -version=2 \
        -path=secret \
        kv || echo "    (KV engine may already be enabled — continuing)"

echo ""
echo "============================================================"
echo "  OpenBao initialization complete!"
echo "============================================================"
echo ""
echo "  Unseal key (SAVE THIS SECURELY — needed after every restart):"
echo "    ${UNSEAL_KEY}"
echo ""
echo "  Root token:"
echo "    ${ROOT_TOKEN}"
echo ""
echo "  Add to your .env file on this server:"
echo "    BAO_TOKEN=${ROOT_TOKEN}"
echo ""
echo "  Then restart api/worker/beat to pick up the token:"
echo "    docker compose up -d api worker beat"
echo ""
echo "  NOTE: OpenBao must be manually unsealed after every restart:"
echo "    docker compose exec openbao bao operator unseal <key>"
echo "============================================================"
