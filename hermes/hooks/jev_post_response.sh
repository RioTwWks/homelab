#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="${JEV_STYLE_VENV:-$HOME/.venvs/jev-style}"
PY="${JEV_STYLE_PYTHON:-}"
if [[ -z "$PY" && -x "$VENV/bin/python" ]]; then
  PY="$VENV/bin/python"
elif [[ -z "$PY" ]]; then
  PY="$(command -v python3)"
fi
exec "$PY" "$ROOT/hermes/hooks/jev_post_response.py"
