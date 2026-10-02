#!/usr/bin/env bash
# Start jev-style local server for guard + quality hooks (loopback only).
set -euo pipefail
VENV="${JEV_STYLE_VENV:-$HOME/.venvs/jev-style}"
BIN="${VENV}/bin/jev-style"
if [[ ! -x "$BIN" ]]; then
  echo "Missing $BIN — create venv and pip install jev-style" >&2
  exit 1
fi
export JEV_STYLE_RELEASE="${JEV_STYLE_RELEASE:-2b-v3}"
HOST="${JEV_STYLE_SERVE_HOST:-127.0.0.1}"
PORT="${JEV_STYLE_SERVE_PORT:-8765}"
exec "$BIN" serve --host "$HOST" --port "$PORT"
