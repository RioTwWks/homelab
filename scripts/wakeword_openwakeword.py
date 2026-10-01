#!/usr/bin/env python3
"""
DEPRECATED (Phase 2): use Hermes `/wake on` — docs/wake-word.md.

Wake word listener using openWakeWord. On detection runs a command (e.g. voice_mvp.sh).

Usage:
  source scripts/voice_mvp.env   # optional: set OPENWAKEWORD_*, WAKE_WORD_* 
  python scripts/wakeword_openwakeword.py [--model_path MODEL] [--command CMD]

Env (or args): OPENWAKEWORD_MODEL (path to .onnx or built-in name), OPENWAKEWORD_BUILTIN (e.g. hey_mycroft),
  WAKE_WORD_COMMAND, WAKE_WORD_THRESHOLD, WAKE_WORD_COOLDOWN_SEC, OPENWAKEWORD_CHUNK_SIZE, OPENWAKEWORD_INFERENCE_FRAMEWORK.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import warnings

# Suppress onnxruntime CUDA warning when GPU is not available (falls back to CPU)
warnings.filterwarnings("ignore", message=".*Specified provider.*available provider.*", category=UserWarning)

import numpy as np
import pyaudio

# Optional: load .env from voice_mvp.env so one can run without sourcing
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
                if k and k not in os.environ and v:
                    os.environ[k] = v

try:
    import inspect
    from openwakeword import utils
    # Older openwakeword: AudioFeatures does not accept inference_framework, but Model passes it
    _AudioFeatures = utils.AudioFeatures
    _sig = inspect.signature(_AudioFeatures.__init__)
    _valid_af_params = set(_sig.parameters) - {"self"}
    _orig_init = _AudioFeatures.__init__

    def _patched_init(self, *args, **kwargs):
        # Model passes inference_framework, wakeword_models, etc.; older AudioFeatures accepts only a subset
        filtered = {k: v for k, v in kwargs.items() if k in _valid_af_params}
        _orig_init(self, *args, **filtered)

    _AudioFeatures.__init__ = _patched_init
    utils.AudioFeatures = _AudioFeatures
    from openwakeword.model import Model
except ImportError as e:
    print("Install: pip install openwakeword pyaudio", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Wake word listener (openWakeWord) → run command on detection")
    parser.add_argument("--model_path", type=str, default=os.environ.get("OPENWAKEWORD_MODEL", ""), help="Path to .onnx model, or built-in name (e.g. hey_mycroft), or empty = all built-in")
    parser.add_argument("--builtin", type=str, default=os.environ.get("OPENWAKEWORD_BUILTIN", ""), help="Comma-separated built-in model names (e.g. hey_mycroft,alexa). Overrides --model_path for built-in choice.")
    parser.add_argument("--command", type=str, default=os.environ.get("WAKE_WORD_COMMAND", ""), help="Command to run on wake word (default: scripts/voice_mvp.sh)")
    parser.add_argument("--threshold", type=float, default=float(os.environ.get("WAKE_WORD_THRESHOLD", "0.6")), help="Detection threshold 0..1 (higher = fewer false triggers from speakers)")
    parser.add_argument("--cooldown_sec", type=float, default=float(os.environ.get("WAKE_WORD_COOLDOWN_SEC", "8")), help="Seconds to wait after command finishes (reduce echo re-triggers)")
    parser.add_argument("--chunk_size", type=int, default=int(os.environ.get("OPENWAKEWORD_CHUNK_SIZE", "1280")), help="Samples per chunk")
    parser.add_argument("--inference_framework", type=str, default=os.environ.get("OPENWAKEWORD_INFERENCE_FRAMEWORK", "onnx"), choices=("onnx", "tflite"))
    parser.add_argument("--list_models", action="store_true", help="List built-in models and exit")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_cmd = os.path.join(script_dir, "voice_mvp.sh")
    command = (args.command or os.environ.get("WAKE_WORD_COMMAND") or default_cmd).strip()
    if not command:
        command = default_cmd

    def load_model():
        # 1) Custom .onnx file
        if args.model_path and os.path.isfile(args.model_path):
            return Model(wakeword_models=[args.model_path], inference_framework=args.inference_framework)
        # 2) Built-in by name(s): OPENWAKEWORD_BUILTIN=hey_mycroft or --builtin hey_mycroft,alexa
        if args.builtin.strip():
            names = [s.strip() for s in args.builtin.split(",") if s.strip()]
            if names:
                return Model(wakeword_models=names, inference_framework=args.inference_framework)
        # 3) Single built-in name in OPENWAKEWORD_MODEL (e.g. OPENWAKEWORD_MODEL=hey_mycroft)
        if args.model_path.strip() and not os.path.isfile(args.model_path):
            return Model(wakeword_models=[args.model_path.strip()], inference_framework=args.inference_framework)
        # 4) All built-in models
        return Model(inference_framework=args.inference_framework)

    try:
        if args.list_models:
            model = load_model()
            print("Built-in models:", list(model.models.keys()))
            return
        oww_model = load_model()
    except TypeError as e:
        if "inference_framework" in str(e) and "AudioFeatures" in str(e):
            print("Your openwakeword version is incompatible (AudioFeatures does not accept inference_framework).", file=sys.stderr)
            print("Upgrade with: pip install -U openwakeword", file=sys.stderr)
            sys.exit(1)
        raise

    if args.model_path and os.path.isfile(args.model_path):
        print(f"Wake word: custom model {args.model_path}", flush=True)
    else:
        if args.model_path and not args.builtin.strip():
            print(f"Model path not found: {args.model_path}, using built-in", file=sys.stderr)
        print("Wake word(s):", list(oww_model.models.keys()), flush=True)

    # Microphone stream (redirect stderr during init to hide ALSA/JACK probe noise)
    rate = 16000
    chunk = args.chunk_size
    stderr_fd = os.dup(2)
    try:
        with open(os.devnull, "w") as devnull:
            os.dup2(devnull.fileno(), 2)
        pa = pyaudio.PyAudio()
        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=rate, input=True, frames_per_buffer=chunk)
    except Exception as e:
        os.dup2(stderr_fd, 2)
        os.close(stderr_fd)
        print(f"Microphone error: {e}", file=sys.stderr)
        sys.exit(1)
    os.dup2(stderr_fd, 2)
    os.close(stderr_fd)

    print(f"Listening (threshold={args.threshold}). On wake word running: {command}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)

    def _drain_mic(n_chunks: int = 5):
        """Read and discard mic data to flush stale audio (echo from speakers)."""
        for _ in range(n_chunks):
            try:
                stream.read(chunk, exception_on_overflow=False)
            except Exception:
                pass

    def _warmup(n_seconds: float = 2.0):
        """Feed real mic audio through the model but ignore scores (flush feature state)."""
        n_chunks_warmup = max(1, int(n_seconds * rate / chunk))
        for _ in range(n_chunks_warmup):
            try:
                buf_w = stream.read(chunk, exception_on_overflow=False)
                audio_w = np.frombuffer(buf_w, dtype=np.int16)
                oww_model.predict(audio_w)
            except Exception:
                pass
        oww_model.reset()  # discard any scores accumulated during warmup

    try:
        while True:
            buf = stream.read(chunk, exception_on_overflow=False)
            audio = np.frombuffer(buf, dtype=np.int16)
            oww_model.predict(audio)

            triggered = False
            for mdl, scores in oww_model.prediction_buffer.items():
                if not scores:
                    continue
                if scores[-1] > args.threshold:
                    triggered = True
                    print(f"Wake word detected ({mdl} score={scores[-1]:.3f}). Running command.", flush=True)

                    # Stop mic while command runs (so TTS playback doesn't feed back)
                    stream.stop_stream()

                    try:
                        subprocess.run(["/usr/bin/env", "bash", "-c", command], cwd=os.path.dirname(script_dir) or ".", check=False)
                    except Exception as e:
                        print(f"Command failed: {e}", file=sys.stderr)

                    # Cooldown, then restart mic and flush buffers + warm up model
                    time.sleep(max(0, args.cooldown_sec))
                    stream.start_stream()
                    _drain_mic(10)
                    oww_model.reset()
                    _warmup(2.0)  # 2s of real mic audio through model, scores discarded
                    print("Listening…", flush=True)
                    break

    except KeyboardInterrupt:
        pass
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()


if __name__ == "__main__":
    main()
