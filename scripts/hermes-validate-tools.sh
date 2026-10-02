#!/usr/bin/env bash
set -euo pipefail
ROOT="${HOMELAB_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export HOMELAB_ROOT="$ROOT"
# shellcheck source=scripts/hermes-env.sh
source "$ROOT/scripts/hermes-env.sh"

VENV="${HERMES_TOOLS_VENV:-$ROOT/.venv-hermes-tools}"
if [[ -x "$VENV/bin/python" ]]; then
  PY="$VENV/bin/python"
elif python3 -c "import pytest" 2>/dev/null; then
  PY=python3
else
  echo "Installing Hermes tool test deps into $VENV ..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r "$ROOT/moltbot_api/requirements.txt" -r "$ROOT/moltbot_api/requirements-dev.txt"
  PY="$VENV/bin/python"
fi

cd "$ROOT"
"$PY" -m pytest hermes/tests/ -v --tb=short
echo "OK: Hermes homelab tools (offline pytest)"
