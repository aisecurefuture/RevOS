#!/usr/bin/env bash
set -euo pipefail

DEALSIG_URL="${DEALSIG_URL:-http://127.0.0.1:8080}"

ready=0
for _attempt in $(seq 1 30); do
  if curl --fail --silent "$DEALSIG_URL/healthz" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  echo "DealSig did not become healthy at $DEALSIG_URL" >&2
  exit 1
fi
curl --fail --silent --show-error "$DEALSIG_URL/" | rg -q "Find the signal"
curl --fail --silent --show-error "$DEALSIG_URL/static/app.css" | rg -q -- "--lime"
echo "DealSig smoke test passed: $DEALSIG_URL"
