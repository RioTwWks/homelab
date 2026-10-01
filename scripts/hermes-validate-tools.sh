#!/usr/bin/env bash
set -euo pipefail
ROOT="${HOMELAB_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
export HOMELAB_ROOT="$ROOT"
source "$ROOT/scripts/hermes-env.sh"
PY=python3
cd "$ROOT" && "$PY" -m pytest hermes/tests/ -v --tb=short
