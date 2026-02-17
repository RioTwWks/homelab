#!/usr/bin/env python3
import argparse
import re
import math
import sys
import warnings
import wave
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

warnings.filterwarnings("ignore", message=r".*Failed to initialize NumPy.*", category=UserWarning)


def _float_samples_to_int16_bytes(samples) -> bytes:
    # samples: 1D float tensor/list in [-1, 1]
    # Avoid numpy dependency: convert via Python lists.
    if hasattr(samples, "detach"):
        samples_list = samples.detach().cpu().flatten().tolist()
    else:
        samples_list = list(samples)

    out = bytearray()
    for x in samples_list:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            x = 0.0
        x = -1.0 if x < -1.0 else (1.0 if x > 1.0 else float(x))
        v = int(round(x * 32767.0))
        if v < -32768:
            v = -32768
        elif v > 32767:
            v = 32767
        out += int(v).to_bytes(2, byteorder="little", signed=True)
    return bytes(out)


def write_wav_int16(path: Path, samples, sample_rate: int, *, pad_ms: int = 0) -> None:
    data = _float_samples_to_int16_bytes(samples)
    if pad_ms > 0:
        pad_samples = int(round(sample_rate * (pad_ms / 1000.0)))
        if pad_samples > 0:
            data = (b"\x00\x00" * pad_samples) + data

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(data)


def _extract_voices(model: Any) -> list[str]:
    voices: list[str] = []
    v = getattr(model, "speakers", None)
    if isinstance(v, (list, tuple)) and v:
        voices = [str(x) for x in v]
    if not voices:
        m = getattr(model, "speaker_to_id", None)
        if isinstance(m, dict) and m:
            voices = sorted(str(k) for k in m.keys())
    return voices


def _normalize_voice(voice: str) -> str:
    v = (voice or "").strip()
    if v.endswith("_v2"):
        v = v[: -len("_v2")]
    if v.endswith("_16khz") or v.endswith("_8khz"):
        v = v.rsplit("_", 1)[0]
    return v


def _normalize_text_ru(text: str) -> str:
    # Basic unit expansions (keep it conservative).
    t = text
    t = t.replace("…", " - ").replace("–", " - ").replace("—", " - ")
    t = t.replace("°C", " градусов").replace("°F", " градусов")
    t = re.sub(r"\bм/с\b", " метров в секунду ", t)
    t = re.sub(r"\bкм/ч\b", " километров в час ", t)
    t = t.replace("%", " процентов ")

    # Spell out common Russian abbreviations (ВСУ -> вэ эс у).
    # Keep "МИД" as a word (requested).
    letter_names = {
        "А": "а",
        "Б": "бэ",
        "В": "вэ",
        "Г": "гэ",
        "Д": "дэ",
        "Е": "е",
        "Ё": "ё",
        "Ж": "жэ",
        "З": "зэ",
        "И": "и",
        "Й": "й",
        "К": "ка",
        "Л": "эл",
        "М": "эм",
        "Н": "эн",
        "О": "о",
        "П": "пэ",
        "Р": "эр",
        "С": "эс",
        "Т": "тэ",
        "У": "у",
        "Ф": "эф",
        "Х": "ха",
        "Ц": "цэ",
        "Ч": "чэ",
        "Ш": "ша",
        "Щ": "ща",
        "Ы": "ы",
        "Э": "э",
        "Ю": "ю",
        "Я": "я",
    }

    def abbr_repl(m: re.Match) -> str:
        s = m.group(0)
        if s == "МИД":
            return s
        parts = [letter_names.get(ch, ch.lower()) for ch in s]
        return " ".join(parts)

    t = re.sub(r"\b[А-ЯЁ]{2,6}\b", abbr_repl, t)

    # Collapse spaces inside number-like sequences so "12 000" → "12000" (one number, not "12" + "000").
    t = re.sub(
        r"\d+(?:\s+\d+)+",
        lambda m: m.group(0).replace(" ", "").replace("\u00a0", ""),
        t,
    )

    # Replace numbers with words (handles ints and decimals, incl. negative).
    try:
        from num2words import num2words
    except Exception:
        return t

    def repl(m: re.Match) -> str:
        s = m.group(0)
        s_norm = s.replace(",", ".")
        try:
            d = Decimal(s_norm)
        except (InvalidOperation, ValueError):
            return s
        try:
            return num2words(d, lang="ru")
        except Exception:
            return s

    t = re.sub(r"(?<!\w)-?\d+(?:[.,]\d+)?(?!\w)", repl, t)
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


def main() -> int:
    p = argparse.ArgumentParser(description="Silero TTS synth to WAV")
    p.add_argument("--text", default=None, help="Text to speak (if omitted, read stdin)")
    p.add_argument("--output", required=True, help="Output WAV path")
    p.add_argument("--language", default="ru")
    p.add_argument("--speaker-model", default="v3_1_ru", help="Model id passed to torch.hub (e.g. v3_1_ru)")
    p.add_argument("--voice", default="ruslan_v2", help="Voice name (e.g. ruslan_v2, kseniya_v2, baya_v2, aidar_v2, ...)")
    p.add_argument("--list-voices", action="store_true", help="Print available voices for this speaker model and exit")
    p.add_argument("--sample-rate", type=int, default=0, help="Sample rate for output WAV (0 = model default)")
    p.add_argument("--pad-ms", type=int, default=80, help="Silence padding at start of audio (ms)")
    p.add_argument("--normalize-ru", action="store_true", help="Normalize Russian text (spell out numbers/units)")
    p.add_argument("--no-normalize-ru", action="store_true", help="Disable Russian text normalization")
    p.add_argument("--device", default="cpu", choices=["cpu"], help="Device (CPU only in this script)")
    args = p.parse_args()

    try:
        import torch  # noqa: F401
    except Exception as e:
        print(f"torch import failed: {e}", file=sys.stderr)
        return 3

    import torch

    device = torch.device("cpu")

    hub_ret = torch.hub.load(
        repo_or_dir="snakers4/silero-models",
        model="silero_tts",
        language=args.language,
        speaker=args.speaker_model,
        trust_repo=True,
        verbose=False,
    )
    # Silero hub API differs across versions:
    # - old: (model, symbols, sample_rate, example_text, apply_tts)
    # - new: (model, example_text) and model has .apply_tts/.save_wav/.symbols/.speakers
    if isinstance(hub_ret, tuple) and len(hub_ret) == 5:
        model, symbols, sample_rate, _, apply_tts = hub_ret
        # Some Silero model wrappers have .to() returning None (in-place).
        _maybe = model.to(device)
        if _maybe is not None:
            model = _maybe
        sr = int(sample_rate)

        voice = _normalize_voice(args.voice)
        if args.list_voices:
            # Old API doesn't expose voices reliably; print known RU set.
            print("aidar_v2\nbaya_v2\nkseniya_v2\nirina_v2\nnatasha_v2\nruslan_v2")
            return 0

        text = args.text if args.text is not None else sys.stdin.read()
        text = (text or "").strip()
        if not text:
            print("empty text", file=sys.stderr)
            return 2
        if args.language.startswith("ru") and (args.normalize_ru or not args.no_normalize_ru):
            text = _normalize_text_ru(text)

        audio = apply_tts(
            texts=[[text]],
            model=model,
            sample_rate=sr,
            symbols=symbols,
            device=device,
            speaker=voice,
        )
        write_wav_int16(Path(args.output), audio, sr, pad_ms=max(0, int(args.pad_ms)))
        return 0

    if not (isinstance(hub_ret, tuple) and len(hub_ret) == 2):
        print(f"unexpected silero hub return: {type(hub_ret)} {hub_ret!r}", file=sys.stderr)
        return 4

    model, _example_text = hub_ret
    _maybe = model.to(device)
    if _maybe is not None:
        model = _maybe
    voices = _extract_voices(model)

    if args.list_voices:
        if voices:
            for v in voices:
                print(v)
            return 0
        # Extremely defensive fallback
        print("aidar\nbaya\nkseniya\nxenia\neugene\nrandom")
        return 0

    voice = _normalize_voice(args.voice)
    if voices and voice not in voices:
        print(f"unknown voice '{args.voice}' (normalized='{voice}'). available: {', '.join(voices)}", file=sys.stderr)
        return 5

    sr = int(args.sample_rate) if int(args.sample_rate) > 0 else int(getattr(model, "sample_rate", 48000))

    text = args.text if args.text is not None else sys.stdin.read()
    text = (text or "").strip()
    if not text:
        print("empty text", file=sys.stderr)
        return 2
    if args.language.startswith("ru") and (args.normalize_ru or not args.no_normalize_ru):
        text = _normalize_text_ru(text)

    audio = model.apply_tts(
        text=text,
        speaker=voice,
        sample_rate=sr,
        put_accent=True,
        put_yo=True,
    )
    write_wav_int16(Path(args.output), audio, sr, pad_ms=max(0, int(args.pad_ms)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

