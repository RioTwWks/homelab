#!/usr/bin/env bash
# Offline validation for docs/remote-access.md + docs/opencode.md (Agent B4 runbook).
set -euo pipefail
ROOT="${HOMELAB_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ROOT"

echo "==> Ansible: playbooks/remote_access.yml (--syntax-check)"
(
  export ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg"
  cd "$ROOT/ansible"
  ansible-playbook playbooks/remote_access.yml --syntax-check
)

echo "==> OpenCode: config/opencode/opencode.json (jq)"
command -v jq >/dev/null || { echo "jq not found"; exit 1; }
jq empty "$ROOT/config/opencode/opencode.json"

if [[ -f "$ROOT/Makefile" ]]; then
  echo "==> Makefile: make check (all playbooks + opencode.json)"
  make check
fi

echo "OK: remote-access + OpenCode runbook checks passed"
