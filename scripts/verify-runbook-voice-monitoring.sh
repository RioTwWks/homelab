#!/usr/bin/env bash
# Offline validation for docs/runbook-voice-monitoring.md (Agent B2).
set -euo pipefail
ROOT="${HOMELAB_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ROOT"

echo "==> Ansible: playbooks/voice.yml (--syntax-check)"
(
  export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"
  cd "$ROOT/ansible"
  ansible-playbook playbooks/voice.yml --syntax-check
)

echo "==> Docker Compose: profile monitoring"
bash "$ROOT/scripts/verify/compose-config.sh" >/dev/null 2>&1 || {
  docker compose -f "$ROOT/docker-compose.yml" --profile monitoring config --quiet
}

echo "==> monitoring/ YAML and JSON"
python3 "$ROOT/scripts/validate_monitoring_configs.py"

echo "==> scripts/flm_validate.sh (bash -n)"
bash -n "$ROOT/scripts/flm_validate.sh"

echo "==> Makefile: voice / install-voice-npu targets"
grep -q '^install-voice:' "$ROOT/Makefile"
grep -q '^install-voice-npu:' "$ROOT/Makefile"

echo "OK: voice + monitoring runbook checks passed (see also: make check, docs/runbook-voice-monitoring.md)"
