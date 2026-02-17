#!/usr/bin/env python3
"""
Timer worker: polls Redis for expired timers and plays a notification via TTS.

Usage:
  python scripts/timer_worker.py

Reads settings from scripts/voice_mvp.env (REDIS_URL, TTS settings, etc.).
Runs as a daemon; stop with Ctrl+C or systemd.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

# Load .env
_ENV_FILE = os.path.join(os.path.dirname(__file__), "voice_mvp.env")
if os.path.isfile(_ENV_FILE):
    with open(_ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                # Expand $HOME, $USER and ~ in values
                v = v.replace("$HOME", os.path.expanduser("~"))
                v = os.path.expandvars(v)
                if v.startswith("~"):
                    v = os.path.expanduser(v)
                if k and v:
                    os.environ[k] = v

try:
    import redis
except ImportError:
    print("Install: pip install redis", file=sys.stderr)
    sys.exit(1)

import json

_TZ = ZoneInfo("Europe/Moscow")
POLL_INTERVAL = int(os.environ.get("TIMER_POLL_INTERVAL", "5"))  # seconds
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
SESSION_ID = os.environ.get("MOLTBOT_SESSION_ID", "home")

# TTS settings (reuse from voice_mvp.env)
TTS_ENGINE = os.environ.get("TTS_ENGINE", "silero")
SILERO_PY = os.environ.get("SILERO_PY", "")
SILERO_LANGUAGE = os.environ.get("SILERO_LANGUAGE", "ru")
SILERO_SPEAKER_MODEL = os.environ.get("SILERO_SPEAKER_MODEL", "v3_1_ru")
SILERO_VOICE = os.environ.get("SILERO_VOICE", "eugene")
SILERO_NORMALIZE_RU = os.environ.get("SILERO_NORMALIZE_RU", "true")
TTS_PAD_MS = os.environ.get("TTS_PAD_MS", "120")
TTS_TEMPO = os.environ.get("TTS_TEMPO", "1.0")
PIPER_BIN = os.environ.get("PIPER_BIN", "piper")
PIPER_MODEL = os.environ.get("PIPER_MODEL", "")
PIPER_SPEAKER = os.environ.get("PIPER_SPEAKER", "0")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
TMP_DIR = os.environ.get("TMPDIR", "/tmp") + "/moltbot-timer"
os.makedirs(TMP_DIR, exist_ok=True)
WAV_OUT = os.path.join(TMP_DIR, "timer_notify.wav")


def speak(text: str) -> None:
    """Generate TTS and play via aplay."""
    if TTS_ENGINE == "silero" and SILERO_PY:
        normalize_args = []
        if SILERO_LANGUAGE.startswith("ru"):
            if SILERO_NORMALIZE_RU == "true":
                normalize_args = ["--normalize-ru"]
            else:
                normalize_args = ["--no-normalize-ru"]

        tts_result = subprocess.run(
            [
                SILERO_PY,
                os.path.join(SCRIPT_DIR, "silero_tts.py"),
                "--text", text,
                "--output", WAV_OUT,
                "--language", SILERO_LANGUAGE,
                "--speaker-model", SILERO_SPEAKER_MODEL,
                "--voice", SILERO_VOICE,
                "--pad-ms", TTS_PAD_MS,
            ] + normalize_args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
        if tts_result.returncode != 0:
            print(f"Silero TTS failed (rc={tts_result.returncode}): {tts_result.stderr.decode(errors='replace').strip()}", file=sys.stderr, flush=True)
    elif TTS_ENGINE == "piper" and PIPER_MODEL:
        proc = subprocess.Popen(
            [PIPER_BIN, "--model", PIPER_MODEL, "--speaker", PIPER_SPEAKER, "--output_file", WAV_OUT],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
        )
        proc.communicate(input=text.encode())
    else:
        print(f"TTS not configured (TTS_ENGINE={TTS_ENGINE})", file=sys.stderr)
        return

    # Apply tempo if needed
    if TTS_TEMPO not in ("1", "1.0"):
        tmp_wav = os.path.join(TMP_DIR, "timer_tempo.wav")
        subprocess.run(
            ["sox", WAV_OUT, tmp_wav, "tempo", "-s", TTS_TEMPO],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if os.path.isfile(tmp_wav):
            os.replace(tmp_wav, WAV_OUT)

    # Play
    if os.path.isfile(WAV_OUT):
        result = subprocess.run(
            ["timeout", "30", "aplay", WAV_OUT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            print(f"aplay failed (rc={result.returncode}): {result.stderr.decode(errors='replace').strip()}", file=sys.stderr, flush=True)
        else:
            print("Audio played OK", flush=True)
    else:
        print(f"WAV file not found: {WAV_OUT}", file=sys.stderr, flush=True)


def check_timers(r: redis.Redis) -> None:
    """Check for expired timers and fire them."""
    list_key = f"timers:list:{SESSION_ID}"
    raw = r.get(list_key)
    if not raw:
        return

    try:
        timer_ids = json.loads(raw)
    except Exception:
        return

    now = datetime.now(_TZ)
    fired_ids: list[str] = []

    for timer_id in timer_ids:
        raw_timer = r.get(timer_id)
        if not raw_timer:
            fired_ids.append(timer_id)  # expired from Redis (TTL), remove from list
            continue

        try:
            timer_data = json.loads(raw_timer)
        except Exception:
            continue

        trigger_at = datetime.fromisoformat(timer_data["trigger_at"])
        if trigger_at <= now:
            # Timer fired! Remove from Redis first to avoid infinite loop
            r.delete(timer_id)
            fired_ids.append(timer_id)

            timer_type = timer_data.get("type", "timer")
            message = timer_data.get("message")

            type_names = {"timer": "Таймер", "alarm": "Будильник", "reminder": "Напоминание"}
            type_name = type_names.get(timer_type, "Таймер")

            if message:
                text = f"{type_name} сработал. {message}."
            else:
                text = f"{type_name} сработал."

            print(f"[{now.strftime('%H:%M:%S')}] {text}", flush=True)
            try:
                speak(text)
            except Exception as e:
                print(f"TTS error: {e}", file=sys.stderr, flush=True)

    # Update timer list (remove fired)
    if fired_ids:
        remaining = [tid for tid in timer_ids if tid not in fired_ids]
        if remaining:
            r.set(list_key, json.dumps(remaining))
        else:
            r.delete(list_key)


def main() -> None:
    print(f"Timer worker started (poll every {POLL_INTERVAL}s, session={SESSION_ID})", flush=True)
    print(f"TTS: {TTS_ENGINE}, Redis: {REDIS_URL}", flush=True)

    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

    # Test connection
    try:
        r.ping()
    except Exception as e:
        print(f"Redis connection failed: {e}", file=sys.stderr)
        sys.exit(1)

    print("Connected to Redis. Watching for timers…", flush=True)

    try:
        while True:
            try:
                check_timers(r)
            except Exception as e:
                print(f"Error checking timers: {e}", file=sys.stderr)
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        pass

    print("Timer worker stopped.", flush=True)


if __name__ == "__main__":
    main()
