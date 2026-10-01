#!/usr/bin/env bash
# Smoke tests for Phase 3 Jev hooks (offline hard rules + fake quality).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${JEV_STYLE_VENV:-$HOME/.venvs/jev-style}"
if [[ -x "$VENV/bin/python" ]]; then
  export JEV_STYLE_PYTHON="$VENV/bin/python"
elif [[ -z "${JEV_STYLE_PYTHON:-}" ]]; then
  export JEV_STYLE_PYTHON="$(command -v python3)"
fi
if ! "$JEV_STYLE_PYTHON" -c "import jev_style" 2>/dev/null; then
  echo "Installing jev-style into temp venv..."
  python3 -m venv "$ROOT/.venv-jev-ci"
  "$ROOT/.venv-jev-ci/bin/pip" install -q 'jev-style>=0.3' pytest
  export JEV_STYLE_PYTHON="$ROOT/.venv-jev-ci/bin/python"
fi
if ! "$JEV_STYLE_PYTHON" -c "import pytest" 2>/dev/null; then
  "$JEV_STYLE_PYTHON" -m pip install -q pytest
fi
cd "$ROOT"
"$JEV_STYLE_PYTHON" -m pytest hermes/tests/test_jev_hooks.py -v --tb=short
echo "OK: jev hooks offline tests passed"
