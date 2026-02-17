#!/usr/bin/env bash
set -euo pipefail

# Compare whisper-server CPU (-ng) vs Vulkan (default) on multiple models.
# Uses the same WAV sample for all runs.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/scripts/voice_mvp.env"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
fi

: "${WHISPER_CPP_DIR:=$HOME/.local/src/whisper.cpp}"
: "${WHISPER_LANG:=ru}"

: "${WHISPER_SERVER_HOST:=127.0.0.1}"
: "${WHISPER_SERVER_PORT:=8099}"
: "${WHISPER_SERVER_URL:=http://${WHISPER_SERVER_HOST}:${WHISPER_SERVER_PORT}}"

: "${COMPARE_THREADS:=10}"
: "${COMPARE_BEST_OF:=1}"
: "${COMPARE_BEAM_SIZE:=1}"
: "${COMPARE_RUNS:=2}"
: "${COMPARE_STARTUP_WAIT_SECONDS:=20}"

# Space-separated list of absolute paths to models
: "${COMPARE_MODELS:=$HOME/.local/src/whisper.cpp/models/ggml-small.bin $HOME/.local/src/whisper.cpp/models/ggml-medium.bin $HOME/.local/src/whisper.cpp/models/ggml-medium-q5_0.bin}"

# Backends: "cpu vulkan"
: "${COMPARE_BACKENDS:=cpu vulkan}"

# WAV source: if not provided, record a short sample
: "${BENCH_WAV:=}"
: "${BENCH_RECORD_SECONDS:=6}"
: "${BENCH_ALSA_DEVICE:=default}"

die() { echo "ERROR: $*" >&2; exit 1; }
ms_now() { date +%s%3N; }

command -v curl >/dev/null 2>&1 || die "curl not found"
command -v jq >/dev/null 2>&1 || die "jq not found"
command -v arecord >/dev/null 2>&1 || die "arecord not found (alsa-utils)"

BIN="${WHISPER_CPP_DIR}/build/bin/whisper-server"
[[ -x "${BIN}" ]] || die "whisper-server not found at ${BIN} (build whisper.cpp)"

TMP_DIR="${TMPDIR:-/tmp}/moltbot-whisper-compare"
mkdir -p "${TMP_DIR}"

if [[ -z "${BENCH_WAV}" ]]; then
  BENCH_WAV="${TMP_DIR}/bench.wav"
  echo "Recording benchmark WAV (${BENCH_RECORD_SECONDS}s)…"
  arecord -D "${BENCH_ALSA_DEVICE}" -f S16_LE -r 16000 -c 1 -d "${BENCH_RECORD_SECONDS}" "${BENCH_WAV}" >/dev/null 2>&1 \
    || die "Recording failed (device=${BENCH_ALSA_DEVICE})"
fi
[[ -f "${BENCH_WAV}" ]] || die "BENCH_WAV not found: ${BENCH_WAV}"

health() {
  curl -s --max-time 2 "${WHISPER_SERVER_URL%/}/health" 2>/dev/null | jq -r '.status // empty' 2>/dev/null
}

stop_server() {
  pkill -f "whisper-server.*--port ${WHISPER_SERVER_PORT}" >/dev/null 2>&1 || true
  pkill -f "whisper-server.* ${WHISPER_SERVER_PORT}" >/dev/null 2>&1 || true
  sleep 0.2
}

start_server() {
  local model="$1"
  local backend="$2"
  local log="${TMP_DIR}/whisper-server-$(basename "${model}")-${backend}.log"

  stop_server

  GPU_ARGS=()
  if [[ "${backend}" == "cpu" ]]; then
    GPU_ARGS=(-ng)
  fi

  nohup "${BIN}" \
    --host "${WHISPER_SERVER_HOST}" \
    --port "${WHISPER_SERVER_PORT}" \
    -m "${model}" \
    -l "${WHISPER_LANG}" \
    -t "${COMPARE_THREADS}" \
    -bo "${COMPARE_BEST_OF}" \
    -bs "${COMPARE_BEAM_SIZE}" \
    -nt \
    -nlp \
    "${GPU_ARGS[@]}" \
    >"${log}" 2>&1 &

  # Model load time varies a lot (especially large-v3). Wait up to COMPARE_STARTUP_WAIT_SECONDS.
  max_tries=$((COMPARE_STARTUP_WAIT_SECONDS * 10))
  for _ in $(seq 1 "${max_tries}"); do
    if [[ "$(health)" == "ok" ]]; then
      return 0
    fi
    sleep 0.1
  done

  echo "Server failed to become healthy. Log (tail):"
  tail -n 60 "${log}" || true
  return 1
}

infer_ms() {
  local t0 t1 resp text
  t0="$(ms_now)"
  resp="$(curl -sS "${WHISPER_SERVER_URL%/}/inference" \
    -H "Content-Type: multipart/form-data" \
    -F file="@${BENCH_WAV}" \
    -F language="${WHISPER_LANG}" \
    -F temperature="0.0" \
    -F temperature_inc="0.2" \
    -F response_format="json")"
  t1="$(ms_now)"
  text="$(jq -r '.text // empty' <<<"${resp}")"
  if [[ -z "${text}" ]]; then
    echo "Inference returned empty text. Response:"
    echo "${resp}"
    return 2
  fi
  echo "$((t1 - t0))"
}

echo
echo "WAV: ${BENCH_WAV}"
echo "Threads: ${COMPARE_THREADS} | best-of: ${COMPARE_BEST_OF} | beam-size: ${COMPARE_BEAM_SIZE} | runs: ${COMPARE_RUNS}"
echo "Backends: ${COMPARE_BACKENDS}"
echo

printf "%-24s %-8s %-10s %-10s\n" "model" "backend" "run_ms" "text_len"
printf "%-24s %-8s %-10s %-10s\n" "-----" "-------" "------" "--------"

for model in ${COMPARE_MODELS}; do
  [[ -f "${model}" ]] || die "Model not found: ${model}"

  for backend in ${COMPARE_BACKENDS}; do
    start_server "${model}" "${backend}" || die "Failed to start server for ${model} (${backend})"

    for _ in $(seq 1 "${COMPARE_RUNS}"); do
      t0="$(ms_now)"
      resp="$(curl -sS "${WHISPER_SERVER_URL%/}/inference" \
        -H "Content-Type: multipart/form-data" \
        -F file="@${BENCH_WAV}" \
        -F language="${WHISPER_LANG}" \
        -F temperature="0.0" \
        -F temperature_inc="0.2" \
        -F response_format="json")"
      t1="$(ms_now)"
      text="$(jq -r '.text // empty' <<<"${resp}")"
      ms="$((t1 - t0))"
      len="${#text}"
      printf "%-24s %-8s %-10s %-10s\n" "$(basename "${model}")" "${backend}" "${ms}" "${len}"
    done
  done
done

echo
echo "Logs: ${TMP_DIR}"

