#!/usr/bin/env bash
# Sourced by ingest.sh / search.sh — sets PY and ensures RAG Python deps.
rag_ensure_python() {
  local VENV="${RAG_VENV:-$ROOT/.venv-rag}"
  local MARKER="$VENV/.rag-requirements-installed"
  local PY_CAND=""

  if [[ -x "$VENV/bin/python" ]]; then
    PY_CAND="$VENV/bin/python"
  elif [[ -x "$VENV/bin/python3" ]]; then
    PY_CAND="$VENV/bin/python3"
  fi

  if [[ -n "$PY_CAND" ]]; then
    if [[ -f "$MARKER" ]] || "$PY_CAND" -c "import httpx" 2>/dev/null; then
      PY="$PY_CAND"
      [[ -f "$MARKER" ]] || touch "$MARKER"
      return 0
    fi
  fi

  # Broken or missing venv (e.g. CI cannot symlink into venv bin).
  [[ -d "$VENV" ]] && rm -rf "$VENV"
  python3 -m venv "$VENV" --copies

  if [[ -x "$VENV/bin/python" ]]; then
    PY="$VENV/bin/python"
  elif [[ -x "$VENV/bin/python3" ]]; then
    PY="$VENV/bin/python3"
  else
    PY="$(command -v python3)"
  fi

  if [[ ! -x "$PY" ]]; then
    echo "rag: no executable python3 (venv: $VENV)" >&2
    exit 1
  fi

  "$PY" -m pip install -q -U pip
  "$PY" -m pip install -q -r "$ROOT/scripts/rag/requirements.txt"
  mkdir -p "$VENV"
  touch "$MARKER"
}
