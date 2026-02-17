#!/usr/bin/env bash
set -euo pipefail

# Helper to run whisper.cpp whisper-server with a preloaded model.
# Keep this running in a separate terminal.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/scripts/voice_mvp.env"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
fi

: "${WHISPER_CPP_DIR:=$HOME/.local/src/whisper.cpp}"
: "${WHISPER_MODEL:=$HOME/.local/src/whisper.cpp/models/ggml-large-v3.bin}"
: "${WHISPER_LANG:=ru}"
: "${WHISPER_SERVER_HOST:=127.0.0.1}"
: "${WHISPER_SERVER_PORT:=8099}"
: "${WHISPER_SERVER_THREADS:=8}"
: "${WHISPER_SERVER_BEST_OF:=1}"
: "${WHISPER_SERVER_BEAM_SIZE:=1}"
: "${WHISPER_SERVER_NO_TIMESTAMPS:=true}"

BIN="${WHISPER_CPP_DIR}/build/bin/whisper-server"
[[ -x "${BIN}" ]] || { echo "Missing whisper-server at ${BIN}. Build whisper.cpp first."; exit 1; }
[[ -f "${WHISPER_MODEL}" ]] || { echo "Missing model at ${WHISPER_MODEL}"; exit 1; }

echo "Starting whisper-server at http://${WHISPER_SERVER_HOST}:${WHISPER_SERVER_PORT}"
echo "Model: ${WHISPER_MODEL}"
echo "Language: ${WHISPER_LANG}"
echo "Threads: ${WHISPER_SERVER_THREADS}"
echo "Best-of: ${WHISPER_SERVER_BEST_OF}"
echo "Beam size: ${WHISPER_SERVER_BEAM_SIZE}"
echo "No timestamps: ${WHISPER_SERVER_NO_TIMESTAMPS}"
echo

NT_ARGS=()
if [[ "${WHISPER_SERVER_NO_TIMESTAMPS}" == "true" ]]; then
  NT_ARGS=(-nt)
fi

exec "${BIN}" \
  --host "${WHISPER_SERVER_HOST}" \
  --port "${WHISPER_SERVER_PORT}" \
  -m "${WHISPER_MODEL}" \
  -l "${WHISPER_LANG}" \
  -t "${WHISPER_SERVER_THREADS}" \
  -bo "${WHISPER_SERVER_BEST_OF}" \
  -bs "${WHISPER_SERVER_BEAM_SIZE}" \
  "${NT_ARGS[@]}" \
  -nlp

