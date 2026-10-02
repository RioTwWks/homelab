#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="${RAG_VENV:-$ROOT/.venv-rag}"
PY="$VENV/bin/python"
if [[ ! -x "$PY" ]]; then
  python3 -m venv "$VENV"
  "$PY" -m pip install -q -U pip
  "$PY" -m pip install -q -r "$ROOT/scripts/rag/requirements.txt"
fi
exec "$PY" "$ROOT/scripts/rag/ingest_homelab.py" "$@"
