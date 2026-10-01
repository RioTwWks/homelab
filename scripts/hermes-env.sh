#!/usr/bin/env bash
set -euo pipefail
export HOMELAB_ROOT="${HOMELAB_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
[[ -f "${HOMELAB_ROOT}/.env" ]] && set -a && source "${HOMELAB_ROOT}/.env" && set +a
export REDIS_URL="${HERMES_REDIS_URL:-redis://127.0.0.1:6379/0}"
export MEDIA_API_BASE_URL="${HERMES_MEDIA_API_BASE_URL:-http://127.0.0.1:8090}"
export SEARXNG_BASE_URL="${HERMES_SEARXNG_BASE_URL:-http://127.0.0.1:18081}"
[[ -n "${HOME_ASSISTANT_URL:-}" ]] && export HOME_ASSISTANT_URL="${HOME_ASSISTANT_URL//host.docker.internal/127.0.0.1}"
