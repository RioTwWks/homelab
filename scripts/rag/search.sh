#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=scripts/rag/ensure_venv.sh
source "$ROOT/scripts/rag/ensure_venv.sh"
rag_ensure_python
exec "$PY" "$ROOT/scripts/rag/search_homelab.py" "$@"
