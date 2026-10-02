#!/usr/bin/env bash
# Health check for speaker-recognition Docker service (default port 8099).
set -euo pipefail

BASE_URL="${SPEAKER_RECOGNITION_URL:-http://127.0.0.1:8099}"
HEALTH_PATH="${SPEAKER_RECOGNITION_HEALTH_PATH:-/health}"

echo "Checking speaker-recognition at ${BASE_URL}${HEALTH_PATH}"
response="$(curl -sfS "${BASE_URL}${HEALTH_PATH}")"
echo "$response" | (command -v jq >/dev/null && jq . || cat)

if command -v jq >/dev/null; then
  status="$(echo "$response" | jq -r '.status // empty')"
  if [[ "$status" != "healthy" ]]; then
    echo "Unexpected status: ${status:-<empty>}" >&2
    exit 1
  fi
fi

echo "OK: speaker-recognition healthy"
