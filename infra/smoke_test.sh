#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [ -f .env ]; then
  ENV_FILE=".env"
elif [ -f .env.example ]; then
  ENV_FILE=".env.example"
else
  echo "ERROR: No .env or .env.example found."
  exit 1
fi

echo "Using env file: $ENV_FILE"

OUTBOUND_ENABLED="$(grep -E '^OUTBOUND_ENABLED=' "$ENV_FILE" | tail -n1 | cut -d'=' -f2- | tr -d '\r')"
TENACIOUS_OUTBOUND_ENABLED="$(grep -E '^TENACIOUS_OUTBOUND_ENABLED=' "$ENV_FILE" | tail -n1 | cut -d'=' -f2- | tr -d '\r')"

if [ -n "$TENACIOUS_OUTBOUND_ENABLED" ] && [ "${TENACIOUS_OUTBOUND_ENABLED,,}" = "true" ]; then
  echo "ERROR: TENACIOUS_OUTBOUND_ENABLED must be false or unset for challenge evaluation."
  exit 1
fi

if [ -n "$OUTBOUND_ENABLED" ] && [ "${OUTBOUND_ENABLED,,}" = "true" ]; then
  echo "ERROR: OUTBOUND_ENABLED must be false or unset for challenge evaluation."
  exit 1
fi

if [ -z "$TENACIOUS_OUTBOUND_ENABLED" ] && [ -z "$OUTBOUND_ENABLED" ]; then
  echo "WARNING: No outbound flag found; prefer TENACIOUS_OUTBOUND_ENABLED=false"
fi

for file in agent/mailersend_client.py agent/sms_client.py agent/main.py; do
  if ! grep -q "outbound_enabled()" "$file"; then
    echo "ERROR: $file must use outbound_enabled() gate helper."
    exit 1
  fi
 done

if ! grep -q "TENACIOUS_OUTBOUND_ENABLED" ".env.example"; then
  echo "ERROR: .env.example must define TENACIOUS_OUTBOUND_ENABLED"
  exit 1
fi

echo "Kill switch smoke test passed."
