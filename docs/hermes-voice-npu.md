# Hermes voice + NPU STT (FastFlowLM)

Homelab redesign **Phase 2** (Hermes wake/STT/TTS) and **Phase 4** (NPU STT).

## Phase 2 acceptance

- `/wake on` fires on **Hey Hermes** (openWakeWord `hey_hermes`)
- STT: RU/EN via `faster-whisper` (`stt.provider: local`, language `ru`)
- TTS: Edge (`ru-RU-DmitryNeural`) + Silero test via `scripts/silero_tts.py`

```bash
make install-voice
hermes doctor
hermes run "Привет, что ты умеешь?"
```

Russian wake **«Привет, Хермес»:** second profile with `wake_word.provider: sherpa`, `phrase: "привет хермес"` ([wake-word.md](./wake-word.md)).

Legacy rollback: `voice_backend: legacy`, enable `whisper-server.service`.

## Phase 4 — `flm validate` and NPU STT

```bash
pip install fastflowlm
bash scripts/flm_validate.sh
bash scripts/flm_validate.sh --json
```

Enable:

```yaml
hermes_enable_npu_stt: true
moltbot_enable_systemd_flm_asr: true
flm_pmode: powersaver
```

```bash
make install-voice-npu
sudo systemctl status flm-asr
```

Hermes uses `http://127.0.0.1:52625/v1` (model `whisper-large-v3-turbo`). Config sets `npu.enabled: true`.

**Acceptance:** `flm validate` OK; wake+STT via FLM; NPU power target < 4 W (measure on host); Ollama LLM unchanged.

Rollback: `hermes_enable_npu_stt: false`, stop `flm-asr`.

## Scripts

| Script | Role |
|--------|------|
| `scripts/flm_validate.sh` | NPU/driver check |
| `scripts/flm_asr_serve.sh` | `flm serve … --asr 1` |
| `scripts/hermes_voice.env.example` | Env template |

Ansible: `ansible/roles/voice/templates/hermes.config.yaml.j2`, `flm-asr.service.j2`.
