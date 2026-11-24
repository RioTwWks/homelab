#!/usr/bin/env bash
# Offline render validation for ansible/roles/voice/templates/hermes.config.yaml.j2.
# Renders the template via Ansible with group_vars/all.yml in both NPU branches
# (hermes_enable_npu_stt on/off) and checks the Hermes config contract:
# valid YAML, context_length >= 65536, STT/TTS/middleware sections, no drift
# between the template and group_vars defaults. Docs: docs/voice-mvp.md,
# docs/hermes-voice-npu.md, docs/runbook-voice-monitoring.md.
set -euo pipefail
ROOT="${HOMELAB_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
TMPL="$ROOT/ansible/roles/voice/templates/hermes.config.yaml.j2"
GROUP_VARS="$ROOT/ansible/group_vars/all.yml"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Self-contained render playbook: minimal generated config keeps it hermetic
# (no dependency on repo ansible.cfg quirks like stdout_callback=yaml, which
# ansible-core >= 2.21 no longer ships, or become defaults).
cat > "$WORK/ansible.cfg" <<'EOF'
[defaults]
interpreter_python = auto_silent
EOF
export ANSIBLE_CONFIG="$WORK/ansible.cfg"

cat > "$WORK/render.yml" <<'EOF'
- name: Render hermes.config.yaml.j2 for offline validation
  hosts: localhost
  connection: local
  gather_facts: false
  become: false
  vars_files:
    - "{{ render_group_vars }}"
  tasks:
    - name: Render template
      ansible.builtin.template:
        src: "{{ render_template }}"
        dest: "{{ render_out }}"
        mode: "0644"
EOF

render() {
  # $1: hermes_enable_npu_stt value, $2: output file
  ansible-playbook "$WORK/render.yml" \
    -e "render_template=$TMPL" \
    -e "render_group_vars=$GROUP_VARS" \
    -e "render_out=$2" \
    -e "moltbot_install_dir=/opt/homelab" \
    -e "hermes_enable_npu_stt=$1" \
    >/dev/null
}

echo "==> Render hermes.config.yaml.j2 (hermes_enable_npu_stt=false -> local faster-whisper)"
render false "$WORK/config-npu-off.yml"

echo "==> Render hermes.config.yaml.j2 (hermes_enable_npu_stt=true -> FLM OpenAI-compatible)"
render true "$WORK/config-npu-on.yml"

echo "==> Validate rendered configs against Hermes contract + group_vars"
python3 - "$GROUP_VARS" "$WORK/config-npu-off.yml" "$WORK/config-npu-on.yml" <<'PY'
import sys
from typing import Any

import yaml


def load_yaml(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    assert isinstance(data, dict), f"{path}: top level must be a mapping"
    return data


def check_common(cfg: dict[str, Any], gv: dict[str, Any], path: str) -> None:
    model = cfg["model"]
    assert model["provider"] == "ollama", f"{path}: model.provider != ollama"
    assert model["base_url"] == gv["hermes_ollama_base_url"], f"{path}: model.base_url drift"
    assert model["model"] == gv["hermes_llm_model"], f"{path}: model.model drift"
    ctx = int(model["context_length"])
    assert ctx >= 65536, f"{path}: context_length {ctx} < 65536 (Hermes requirement)"
    assert ctx == int(gv["hermes_context_length"]), f"{path}: context_length drift vs group_vars"

    skills_paths = cfg["skills"]["paths"]
    assert "/opt/homelab/hermes/skills" in skills_paths, f"{path}: hermes skills path missing"

    assert cfg["wake_word"]["phrase"] == gv["hermes_wake_word_en"], f"{path}: wake word drift"

    tts = cfg["tts"]
    assert tts["provider"] == "edge", f"{path}: tts.provider != edge"
    assert tts["edge"]["voice"] == gv["hermes_edge_voice"], f"{path}: tts.edge.voice drift"

    middleware = cfg["voice"]["middleware"]
    assert isinstance(middleware["enabled"], bool), f"{path}: middleware.enabled not bool"
    assert middleware["url"] == gv["hermes_speaker_middleware_url"], f"{path}: middleware.url drift"

    assert cfg["stt"]["language"] == gv["hermes_stt_language"], f"{path}: stt.language drift"


gv = load_yaml(sys.argv[1])
off = load_yaml(sys.argv[2])
on = load_yaml(sys.argv[3])
check_common(off, gv, sys.argv[2])
check_common(on, gv, sys.argv[3])

# NPU off -> local faster-whisper
assert off["stt"]["provider"] == "local", "NPU off: stt.provider must be local"
assert off["stt"]["local"]["model"] == gv["hermes_faster_whisper_model"], "NPU off: whisper model drift"
assert off["npu"]["enabled"] is False, "NPU off: npu.enabled must be false"

# NPU on -> OpenAI-compatible FLM endpoint
assert on["stt"]["provider"] == "openai", "NPU on: stt.provider must be openai"
expected_flm = f"http://127.0.0.1:{gv['flm_serve_port']}/v1"
assert on["stt"]["openai"]["base_url"] == expected_flm, f"NPU on: FLM base_url != {expected_flm}"
assert on["npu"]["enabled"] is True, "NPU on: npu.enabled must be true"

print("OK: hermes.config.yaml.j2 renders a valid Hermes config in both NPU branches")
PY

echo "OK: hermes config render validation passed"
