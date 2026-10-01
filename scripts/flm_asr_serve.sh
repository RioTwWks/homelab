#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/scripts/hermes_voice.env"
[[ -f "${ENV_FILE}" ]] && source "${ENV_FILE}"
: "${FLM_SERVE_MODEL:=gemma3:1b}"
: "${FLM_SERVE_PORT:=52625}"
: "${FLM_PMODE:=powersaver}"
: "${FLM_SERVE_HOST:=127.0.0.1}"
command -v flm >/dev/null || { echo "Install: pip install fastflowlm" >&2; exit 127; }
exec flm serve "${FLM_SERVE_MODEL}" --asr 1 --pmode "${FLM_PMODE}" --port "${FLM_SERVE_PORT}" --host "${FLM_SERVE_HOST}"
