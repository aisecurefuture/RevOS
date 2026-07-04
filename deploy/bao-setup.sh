#!/usr/bin/env bash
# deploy/bao-setup.sh
#
# One-time OpenBao initialisation helper.
#
# Run this script ONCE after the very first `docker compose up`.
# OpenBao starts in an uninitialized, sealed state — this script:
#   1. Waits for OpenBao HTTP to be reachable.
#   2. Initializes it (1-of-1 unseal key).
#   3. Unseals the instance.
#   4. Enables a KV v2 secrets engine at the "secret" mount.
#   5. Prints the root token so you can add it to .env.
#
# IMPORTANT — production usage:
#   Do NOT use the root token in production.  Instead:
#   • Store the unseal key in a secure key-management service.
#   • Create an AppRole with a scoped policy (read/write revos/*).
#   • Set BAO_TOKEN to the AppRole secret-id / wrapped token.
#   See: https://developer.hashicorp.com/vault/docs/auth/approle
#
# Usage:
#   cd /path/to/RevOS
#   docker compose up -d openbao
#   bash deploy/bao-setup.sh

set -euo pipefail

COMPOSE_SERVICE="openbao"
# Address as seen from inside the container
INTERNAL_ADDR="http://localhost:8200"

# Helper: run a bao CLI command inside the container.
# OpenBao v2 uses BAO_ADDR / BAO_TOKEN env vars (not VAULT_*).
bao_exec() {
    docker compose exec \
        -e "BAO_ADDR=${INTERNAL_ADDR}" \
        -e "VAULT_ADDR=${INTERNAL_ADDR}" \
        "${COMPOSE_SERVICE}" bao "$@"
}

echo "==> Waiting for OpenBao HTTP to be reachable ..."

# Use the health endpoint for liveness — it always returns HTTP even when
# uninitialized or sealed (just with different status codes).
for i in $(seq 1 20); do
    HTTP_CODE=$(docker compose exec "${COMPOSE_SERVICE}" \
        sh -c "wget -qO- -S http://localhost:8200/v1/sys/health 2>&1 | grep 'HTTP/' | awk '{print \$2}' | head -1" \
        2>/dev/null || true)
    if [ -n "${HTTP_CODE}" ]; then
        echo "    OpenBao responding (HTTP ${HTTP_CODE})."
        break
    fi
    echo "    Attempt ${i}/20 — waiting 3 s ..."
    sleep 3
    if [ "${i}" -eq 20 ]; then
        echo "ERROR: OpenBao did not respond after 60 s. Check logs:"
        echo "    docker compose logs openbao"
        exit 1
    fi
done

echo "==> Checking initialisation state ..."

# init-status exits: 0=initialized+unsealed, 1=error, 2=not-initialized, 3=sealed
INIT_STATUS=0
bao_exec operator init -status -format=json > /dev/null 2>&1 || INIT_STATUS=$?

if [ "${INIT_STATUS}" -eq 0 ]; then
    echo "==> OpenBao is already initialized and unsealed — nothing to do."
    exit 0
fi

if [ "${INIT_STATUS}" -eq 3 ]; then
    echo "==> OpenBao is initialized but sealed."
    echo "    Run: docker compose exec openbao bao operator unseal <key>"
    exit 1
fi

if [ "${INIT_STATUS}" -ne 2 ]; then
    echo "ERROR: Unexpected init-status exit code ${INIT_STATUS}. Check logs:"
    echo "    docker compose logs openbao"
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
    -e "BAO_ADDR=${INTERNAL_ADDR}" \
    -e "VAULT_ADDR=${INTERNAL_ADDR}" \
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
echo "  Then restart the api service to pick it up:"
echo "    docker compose up -d api worker beat"
echo ""
echo "  PRODUCTION WARNING:"
echo "    - Do NOT use the root token long-term."
echo "    - Create a scoped AppRole policy for revos/* paths."
echo "    - Store the unseal key in a KMS or Vault auto-unseal."
echo "============================================================"
