#!/usr/bin/env bash
set -euo pipefail

# Benchmark whisper-server throughput by restarting it with different thread counts.
# It runs locally and sends the same WAV via /inference, measuring wall time.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/scripts/voice_mvp.env"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
fi

: "${WHISPER_CPP_DIR:=$HOME/.local/src/whisper.cpp}"
: "${WHISPER_MODEL:=$HOME/.local/src/whisper.cpp/models/ggml-medium.bin}"
: "${WHISPER_LANG:=ru}"
: "${WHISPER_SERVER_HOST:=127.0.0.1}"
: "${WHISPER_SERVER_PORT:=8099}"
: "${WHISPER_SERVER_BEST_OF:=1}"
: "${WHISPER_SERVER_URL:=http://${WHISPER_SERVER_HOST}:${WHISPER_SERVER_PORT}}"

: "${BENCH_WAV:=}"
: "${BENCH_RECORD_SECONDS:=6}"
: "${BENCH_ALSA_DEVICE:=default}"
: "${BENCH_THREADS_LIST:=4 6 8 10 12 14 16}"
: "${BENCH_RUNS:=2}"

die() { echo "ERROR: $*" >&2; exit 1; }
ms_now() { date +%s%3N; }

command -v curl >/dev/null 2>&1 || die "curl not found"
command -v jq >/dev/null 2>&1 || die "jq not found"
command -v arecord >/dev/null 2>&1 || die "arecord not found (alsa-utils)"

BIN="${WHISPER_CPP_DIR}/build/bin/whisper-server"
[[ -x "${BIN}" ]] || die "whisper-server not found at ${BIN}"
[[ -f "${WHISPER_MODEL}" ]] || die "model not found at ${WHISPER_MODEL}"

TMP_DIR="${TMPDIR:-/tmp}/moltbot-whisper-bench"
mkdir -p "${TMP_DIR}"

if [[ -z "${BENCH_WAV}" ]]; then
  BENCH_WAV="${TMP_DIR}/bench.wav"
  echo "Recording benchmark WAV (${BENCH_RECORD_SECONDS}s)…"
  arecord -D "${BENCH_ALSA_DEVICE}" -f S16_LE -r 16000 -c 1 -d "${BENCH_RECORD_SECONDS}" "${BENCH_WAV}" >/dev/null 2>&1 \
    || die "Recording failed (device=${BENCH_ALSA_DEVICE})"
fi

[[ -f "${BENCH_WAV}" ]] || die "BENCH_WAV not found: ${BENCH_WAV}"

echo
echo "Benchmark file: ${BENCH_WAV}"
echo "Model: ${WHISPER_MODEL}"
echo "Language: ${WHISPER_LANG}"
echo "Server: ${WHISPER_SERVER_URL}"
echo "Runs per setting: ${BENCH_RUNS}"
echo

health() {
  # Keep startup polling quiet (no curl connection errors in output)
  curl -s --max-time 2 "${WHISPER_SERVER_URL%/}/health" 2>/dev/null | jq -r '.status // empty' 2>/dev/null
}

start_server() {
  local threads="$1"
  echo "Starting whisper-server (threads=${threads})…"
  # Stop any existing instance on this port (best-effort)
  pkill -f "whisper-server.*--port ${WHISPER_SERVER_PORT}" >/dev/null 2>&1 || true
  sleep 0.2
  nohup "${BIN}" \
    --host "${WHISPER_SERVER_HOST}" \
    --port "${WHISPER_SERVER_PORT}" \
    -m "${WHISPER_MODEL}" \
    -l "${WHISPER_LANG}" \
    -t "${threads}" \
    -bo "${WHISPER_SERVER_BEST_OF}" \
    -nlp \
    >"${TMP_DIR}/whisper-server-${threads}.log" 2>&1 &

  # Wait until healthy
  for _ in $(seq 1 50); do
    if [[ "$(health)" == "ok" ]]; then
      return 0
    fi
    sleep 0.1
  done
  echo "Server failed to become healthy. Log (tail):"
  tail -n 40 "${TMP_DIR}/whisper-server-${threads}.log" || true
  return 1
}

infer_once_ms() {
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
    echo "Empty transcription. Response:"
    echo "${resp}"
    return 2
  fi
  echo "$((t1 - t0))"
}

printf "%-10s %-10s %-10s\n" "threads" "run_ms" "text_len"
printf "%-10s %-10s %-10s\n" "------" "------" "--------"

for threads in ${BENCH_THREADS_LIST}; do
  start_server "${threads}" || die "Failed to start server for threads=${threads}"

  for run in $(seq 1 "${BENCH_RUNS}"); do
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
    printf "%-10s %-10s %-10s\n" "${threads}" "${ms}" "${len}"
  done
done

echo
echo "Logs saved under: ${TMP_DIR}"

