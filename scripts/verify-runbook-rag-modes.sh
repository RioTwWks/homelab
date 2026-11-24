#!/usr/bin/env bash
# Offline validation for docs/rag-qdrant.md + docs/homelab-modes.md (Agent B3 runbook).
set -euo pipefail
ROOT="${HOMELAB_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ROOT"

echo "==> docker compose: qdrant in base stack"
docker compose -f docker-compose.yml config --quiet
grep -qE '^  qdrant:' "$ROOT/docker-compose.yml"

echo "==> homelab_mode.sh: bash -n"
bash -n "$ROOT/scripts/homelab_mode.sh"

echo "==> moltbot_api: test_homelab_mode.py"
API_VENV="${MOLTBOT_API_VENV:-$ROOT/moltbot_api/.venv}"
API_PY=""
if [[ -x "$API_VENV/bin/python" ]]; then
  API_PY="$API_VENV/bin/python"
fi
if [[ -z "$API_PY" ]]; then
  # GitHub Actions can fail to symlink python into a venv, leaving a
  # non-executable bin/python — recreate with --copies, like ensure_venv.sh.
  [[ -d "$API_VENV" ]] && rm -rf "$API_VENV"
  python3 -m venv "$API_VENV" --copies
  if [[ -x "$API_VENV/bin/python" ]]; then
    API_PY="$API_VENV/bin/python"
  else
    API_PY="$(command -v python3)"
  fi
  "$API_PY" -m pip install -q -U pip
  "$API_PY" -m pip install -q -r "$ROOT/moltbot_api/requirements.txt" -r "$ROOT/moltbot_api/requirements-dev.txt"
fi
"$API_PY" -m pytest "$ROOT/moltbot_api/tests/test_homelab_mode.py" -q

echo "==> RAG: ingest --dry-run"
bash "$ROOT/scripts/rag/ingest.sh" --dry-run >/dev/null

if curl -sf "${QDRANT_URL:-http://localhost:6333}/healthz" >/dev/null 2>&1; then
  echo "==> RAG: fake-embeddings smoke (qdrant reachable)"
  bash "$ROOT/scripts/rag/ingest.sh" --fake-embeddings --limit-chunks 5
  bash "$ROOT/scripts/rag/search.sh" --fake-embeddings "docker compose" | head -3
else
  echo "SKIP: Qdrant not reachable (${QDRANT_URL:-http://localhost:6333}); docker compose up -d qdrant for full RAG smoke"
fi

echo "OK: RAG + homelab modes runbook checks passed"
