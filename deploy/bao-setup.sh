#!/usr/bin/env bash
# deploy/bao-setup.sh
#
# One-time OpenBao initialisation helper.
#
# Run this script ONCE after the very first `docker compose up`.
# OpenBao starts in an uninitialized, sealed state — this script:
#   1. Detects whether Bao is already initialized.
#   2. Initializes it (1-of-1 unseal key; dev simplicity, see prod note).
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

BAO_ADDR="${BAO_ADDR:-http://localhost:8200}"
COMPOSE_SERVICE="openbao"

# Helper: run a bao command inside the container.
bao() {
    docker compose exec -e "VAULT_ADDR=${BAO_ADDR}" "${COMPOSE_SERVICE}" bao "$@"
}

echo "==> Checking OpenBao status at ${BAO_ADDR} ..."

# Wait briefly for the service to be up (it may still be starting).
for i in $(seq 1 10); do
    if bao status > /dev/null 2>&1; then
        break
    fi
    echo "    Waiting for OpenBao to respond (attempt ${i}/10) ..."
    sleep 2
done

# Check initialization status (exit code 2 = not initialized, 0 = initialized+unsealed, 1 = error).
INIT_STATUS=0
bao operator init-status > /dev/null 2>&1 || INIT_STATUS=$?

if [ "${INIT_STATUS}" -eq 0 ]; then
    echo "==> OpenBao is already initialized and unsealed — nothing to do."
    echo "    If you need to retrieve the root token, check your secure backup."
    exit 0
fi

if [ "${INIT_STATUS}" -ne 2 ]; then
    echo "==> OpenBao returned unexpected status (exit ${INIT_STATUS}). Check logs:"
    echo "    docker compose logs openbao"
    exit 1
fi

echo "==> Initializing OpenBao (1 key share, threshold 1) ..."
INIT_OUTPUT=$(bao operator init \
    -key-shares=1 \
    -key-threshold=1 \
    -format=json)

UNSEAL_KEY=$(echo "${INIT_OUTPUT}" | grep -o '"unseal_keys_b64":\["[^"]*"' | cut -d'"' -f4)
ROOT_TOKEN=$(echo "${INIT_OUTPUT}" | grep -o '"root_token":"[^"]*"' | cut -d'"' -f4)

if [ -z "${UNSEAL_KEY}" ] || [ -z "${ROOT_TOKEN}" ]; then
    echo "ERROR: Failed to parse init output. Raw output:"
    echo "${INIT_OUTPUT}"
    exit 1
fi

echo "==> Unsealing OpenBao ..."
bao operator unseal "${UNSEAL_KEY}"

echo "==> Enabling KV v2 secrets engine at 'secret/' ..."
VAULT_TOKEN="${ROOT_TOKEN}" bao secrets enable \
    -version=2 \
    -path=secret \
    kv || echo "    (KV engine may already be enabled — continuing)"

echo ""
echo "============================================================"
echo "  OpenBao initialization complete!"
echo "============================================================"
echo ""
echo "  Unseal key (store this securely!):"
echo "    ${UNSEAL_KEY}"
echo ""
echo "  Root token:"
echo "    ${ROOT_TOKEN}"
echo ""
echo "  Add the following to your .env file:"
echo "    BAO_TOKEN=${ROOT_TOKEN}"
echo ""
echo "  PRODUCTION WARNING:"
echo "    - Do NOT use the root token in production."
echo "    - Create a scoped AppRole policy for revos/* paths."
echo "    - Store the unseal key in a KMS (AWS KMS, GCP KMS, etc.)"
echo "      or use Vault's auto-unseal feature."
echo "    - See: https://developer.hashicorp.com/vault/docs/auth/approle"
echo "============================================================"
