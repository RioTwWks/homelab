#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/scripts/voice_mvp.env"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
else
  echo "Missing ${ENV_FILE}. Copy scripts/voice_mvp.env.example -> scripts/voice_mvp.env and edit it."
  exit 1
fi

: "${MOLTBOT_API_BASE_URL:=http://localhost:18080}"
: "${MOLTBOT_SESSION_ID:=home}"
: "${RECORD_SECONDS:=6}"
: "${ALSA_DEVICE:=default}"
: "${RECORD_UNTIL_SILENCE:=false}"
: "${MAX_RECORD_SECONDS:=12}"
: "${SILENCE_STOP_SECONDS:=0.8}"
: "${SILENCE_THRESHOLD_PCT:=2}"
: "${WHISPER_CPP_DIR:?Set WHISPER_CPP_DIR}"
: "${WHISPER_MODEL:?Set WHISPER_MODEL}"
: "${WHISPER_LANG:=ru}"
: "${WHISPER_SERVER_URL:=}"
: "${WHISPER_PROMPT:=}"
: "${TTS_ENGINE:=piper}"
: "${PIPER_MODEL:=}"
: "${PIPER_SPEAKER:=0}"
: "${PIPER_BIN:=piper}"
: "${SILERO_PY:=}"
: "${SILERO_LANGUAGE:=ru}"
: "${SILERO_SPEAKER_MODEL:=v3_1_ru}"
: "${SILERO_VOICE:=ruslan_v2}"
: "${SILERO_NORMALIZE_RU:=true}"
: "${TTS_PAD_MS:=120}"
: "${TTS_TEMPO:=1.0}"
: "${NEWS_ITEM_PAUSE_SECONDS:=0.35}"
: "${VERBOSE:=0}"

TMP_DIR="${TMPDIR:-/tmp}/moltbot-voice"
mkdir -p "${TMP_DIR}"

WAV_IN="${TMP_DIR}/in.wav"
WAV_SEND="${TMP_DIR}/send.wav"
WHISPER_OUT_PREFIX="${TMP_DIR}/whisper"
WHISPER_TXT="${WHISPER_OUT_PREFIX}.txt"
WAV_OUT="${TMP_DIR}/out.wav"
WHISPER_LOG="${TMP_DIR}/whisper.log"
REC_LOG="${TMP_DIR}/rec.log"

command -v arecord >/dev/null 2>&1 || die "arecord not found. Install alsa-utils."
command -v aplay >/dev/null 2>&1 || die "aplay not found. Install alsa-utils."
command -v jq >/dev/null 2>&1 || die "jq not found. Install jq."
command -v curl >/dev/null 2>&1 || die "curl not found. Install curl."
if [[ "${TTS_ENGINE}" == "piper" ]]; then
  [[ -n "${PIPER_MODEL}" ]] || die "TTS_ENGINE=piper but PIPER_MODEL is empty"
  [[ -f "${PIPER_MODEL}" ]] || die "PIPER_MODEL not found: ${PIPER_MODEL}"
  if [[ "${PIPER_BIN}" == "piper" ]]; then
    command -v piper >/dev/null 2>&1 || die "piper not found. Install piper-tts (see docs/voice-mvp.md)."
  else
    [[ -x "${PIPER_BIN}" ]] || die "PIPER_BIN not executable: ${PIPER_BIN}"
  fi
elif [[ "${TTS_ENGINE}" == "silero" ]]; then
  [[ -n "${SILERO_PY}" ]] || die "TTS_ENGINE=silero but SILERO_PY is empty (set it to venv python)"
  [[ -x "${SILERO_PY}" ]] || die "SILERO_PY not executable: ${SILERO_PY}"
else
  die "Unknown TTS_ENGINE: ${TTS_ENGINE} (use piper or silero)"
fi

[[ -d "${WHISPER_CPP_DIR}" ]] || die "WHISPER_CPP_DIR does not exist: ${WHISPER_CPP_DIR}"
[[ -f "${WHISPER_MODEL}" ]] || die "WHISPER_MODEL not found: ${WHISPER_MODEL} (download it in whisper.cpp models/)"

WHISPER_CLI_BIN=""
if [[ -x "${WHISPER_CPP_DIR}/build/bin/whisper-cli" ]]; then
  WHISPER_CLI_BIN="${WHISPER_CPP_DIR}/build/bin/whisper-cli"
elif [[ -x "${WHISPER_CPP_DIR}/build/bin/main" ]]; then
  # older build name
  WHISPER_CLI_BIN="${WHISPER_CPP_DIR}/build/bin/main"
elif command -v whisper-cli >/dev/null 2>&1; then
  WHISPER_CLI_BIN="$(command -v whisper-cli)"
fi
if [[ -z "${WHISPER_SERVER_URL}" ]]; then
  [[ -n "${WHISPER_CLI_BIN}" ]] || die "whisper-cli not found. Build whisper.cpp (see docs/voice-mvp.md). Expected: ${WHISPER_CPP_DIR}/build/bin/whisper-cli"
fi

if [[ "${RECORD_UNTIL_SILENCE}" == "true" ]]; then
  # Use SoX `rec` to stop when silence is detected.
  if ! command -v rec >/dev/null 2>&1; then
    die "RECORD_UNTIL_SILENCE=true but 'rec' not found. Install sox: sudo apt install -y sox"
  fi
  echo "Recording (until silence, max ${MAX_RECORD_SECONDS}s) from ALSA device: ${ALSA_DEVICE}"
  # Note: for ALSA device selection, SoX supports -d (default). For custom devices,
  # it's more reliable to keep ALSA_DEVICE=default and select mic in OS settings.
  # Stop when we observe SILENCE_STOP_SECONDS of near-silence.
  # Some ALSA backends print warnings; capture them into a log file.
  rec -q -t wav -r 16000 -c 1 -b 16 -e signed-integer "${WAV_IN}" trim 0 "${MAX_RECORD_SECONDS}" \
    silence 1 0.10 "${SILENCE_THRESHOLD_PCT}%" 1 "${SILENCE_STOP_SECONDS}" "${SILENCE_THRESHOLD_PCT}%" \
    > /dev/null 2>"${REC_LOG}" || die "Recording (rec) failed."
else
  echo "Recording (${RECORD_SECONDS}s) from ALSA device: ${ALSA_DEVICE}"
  if ! arecord -D "${ALSA_DEVICE}" -f S16_LE -r 16000 -c 1 -d "${RECORD_SECONDS}" "${WAV_IN}" >/dev/null 2>&1; then
    die "Recording failed. Check ALSA device name (ALSA_DEVICE) and permissions."
  fi
fi

# Re-encode to a clean WAV for whisper-server (avoids occasional 'failed to read audio data')
if command -v sox >/dev/null 2>&1; then
  sox "${WAV_IN}" -t wav -r 16000 -c 1 -b 16 -e signed-integer "${WAV_SEND}" >/dev/null 2>&1 \
    || die "sox failed to re-encode WAV (check recording)."
else
  WAV_SEND="${WAV_IN}"
fi

if [[ ! -s "${WAV_SEND}" ]] || [[ "$(wc -c < "${WAV_SEND}")" -lt 8000 ]]; then
  die "Recorded WAV looks too small. Try adjusting SILENCE_* settings or speak louder. (file=${WAV_SEND})"
fi

echo "Transcribing (whisper.cpp)…"
rm -f "${WHISPER_TXT}" "${WHISPER_LOG}"

if [[ -n "${WHISPER_SERVER_URL}" ]]; then
  # Pre-warmed server mode (faster, no model load each run)
  HEALTH_URL="${WHISPER_SERVER_URL%/}/health"
  if ! curl -sS --max-time 2 "${HEALTH_URL}" >/dev/null 2>&1; then
    echo "WARNING: whisper-server not reachable at ${HEALTH_URL}"
    echo "Start it with: bash scripts/whisper_server_run.sh"
  fi

  RESP_JSON="$(curl -sS "${WHISPER_SERVER_URL%/}/inference" \
    -H "Content-Type: multipart/form-data" \
    -F file="@${WAV_SEND}" \
    -F language="${WHISPER_LANG}" \
    -F no_timestamps="true" \
    -F suppress_nst="true" \
    ${WHISPER_PROMPT:+-F prompt="${WHISPER_PROMPT}"} \
    -F temperature="0.0" \
    -F temperature_inc="0.2" \
    -F response_format="json")" || {
      echo "Whisper server request failed."
      exit 2
    }

  USER_TEXT="$(jq -r '.text // empty' <<<"${RESP_JSON}")"
  if [[ -z "${USER_TEXT}" ]]; then
    echo "Empty transcription from whisper-server. Full response:"
    echo "${RESP_JSON}"
    exit 2
  fi
else
  # Local CLI mode (slower; loads model each run)
  set +e
  "${WHISPER_CLI_BIN}" \
    -m "${WHISPER_MODEL}" \
    -f "${WAV_IN}" \
    -l "${WHISPER_LANG}" \
    -otxt -of "${WHISPER_OUT_PREFIX}" \
    >"${WHISPER_LOG}" 2>&1
  WHISPER_RC=$?
  set -e
  if [[ "${WHISPER_RC}" != "0" ]]; then
    echo "Whisper failed (exit ${WHISPER_RC}). Log:"
    sed -n '1,120p' "${WHISPER_LOG}" || true
    exit 2
  fi
  if [[ "${VERBOSE}" == "1" ]]; then
    echo "Whisper log (head):"
    sed -n '1,40p' "${WHISPER_LOG}" || true
  fi

  if [[ ! -s "${WHISPER_TXT}" ]]; then
    echo "No transcription output at ${WHISPER_TXT}"
    echo "Whisper log (head):"
    sed -n '1,120p' "${WHISPER_LOG}" || true
    exit 2
  fi

  USER_TEXT="$(tr '\n' ' ' < "${WHISPER_TXT}" | sed -E 's/[[:space:]]+/ /g' | sed -E 's/^ +| +$//g')"
fi

if [[ -z "${USER_TEXT}" ]]; then
  echo "Empty transcription."
  exit 3
fi

echo "You said: ${USER_TEXT}"

JSON_PAYLOAD="$(jq -cn --arg text "${USER_TEXT}" --arg session_id "${MOLTBOT_SESSION_ID}" '{text:$text,session_id:$session_id}')"
REPLY_JSON="$(curl -sS "${MOLTBOT_API_BASE_URL}/v1/chat" -H 'content-type: application/json' -d "${JSON_PAYLOAD}")"
REPLY_TEXT="$(jq -r '.reply_text // empty' <<<"${REPLY_JSON}")"
REPLY_INTENT="$(jq -r '.intent // empty' <<<"${REPLY_JSON}")"

if [[ -z "${REPLY_TEXT}" ]]; then
  echo "Empty reply_text. Full response:"
  echo "${REPLY_JSON}"
  exit 4
fi

echo "Assistant: ${REPLY_TEXT}"

speak_one() {
  local text="$1"

  if [[ "${TTS_ENGINE}" == "piper" ]]; then
    printf "%s" "${text}" | "${PIPER_BIN}" \
      --model "${PIPER_MODEL}" \
      --speaker "${PIPER_SPEAKER}" \
      --output_file "${WAV_OUT}" \
      >/dev/null
  else
    SILERO_NORMALIZE_ARGS=()
    if [[ "${SILERO_LANGUAGE}" == ru* ]]; then
      if [[ "${SILERO_NORMALIZE_RU}" == "true" ]]; then
        SILERO_NORMALIZE_ARGS+=(--normalize-ru)
      else
        SILERO_NORMALIZE_ARGS+=(--no-normalize-ru)
      fi
    fi
    "${SILERO_PY}" "${ROOT_DIR}/scripts/silero_tts.py" \
      --text "${text}" \
      --output "${WAV_OUT}" \
      --language "${SILERO_LANGUAGE}" \
      --speaker-model "${SILERO_SPEAKER_MODEL}" \
      --voice "${SILERO_VOICE}" \
      --pad-ms "${TTS_PAD_MS}" \
      "${SILERO_NORMALIZE_ARGS[@]}" \
      >/dev/null
  fi

  if [[ "${TTS_TEMPO}" != "1" && "${TTS_TEMPO}" != "1.0" ]]; then
    if ! command -v sox >/dev/null 2>&1; then
      die "TTS_TEMPO=${TTS_TEMPO} set but sox not found. Install sox or set TTS_TEMPO=1.0"
    fi
    WAV_OUT_TMP="${TMP_DIR}/out_tempo.wav"
    sox "${WAV_OUT}" "${WAV_OUT_TMP}" tempo -s "${TTS_TEMPO}" >/dev/null 2>&1 \
      || die "sox tempo failed (TTS_TEMPO=${TTS_TEMPO})"
    mv "${WAV_OUT_TMP}" "${WAV_OUT}"
  fi

  # Таймаут aplay, чтобы не зависнуть при занятом ALSA (например, второй запуск по wake word)
  TTS_PLAY_TIMEOUT="${TTS_PLAY_TIMEOUT:-30}"
  timeout "${TTS_PLAY_TIMEOUT}" aplay "${WAV_OUT}" >/dev/null 2>&1 || true
}

if [[ "${TTS_ENGINE}" == "piper" ]]; then
  echo "Speaking (piper)…"
else
  echo "Speaking (silero)…"
fi

if [[ "${REPLY_INTENT}" == "news" ]]; then
  # Speak each bullet with a short pause.
  while IFS= read -r line; do
    line="${line#- }"
    line="$(sed -E 's/^[[:space:]]+|[[:space:]]+$//g' <<<"${line}")"
    [[ -z "${line}" ]] && continue
    speak_one "${line}"
    sleep "${NEWS_ITEM_PAUSE_SECONDS}"
  done <<<"${REPLY_TEXT}"
else
  speak_one "${REPLY_TEXT}"
fi

