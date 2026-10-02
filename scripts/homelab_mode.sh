#!/usr/bin/env bash
set -euo pipefail
R="${HOMELAB_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
S="${HOMELAB_MODE_STATE_FILE:-$R/runtime/homelab-mode/state.json}"
C="${HOMELAB_COMPOSE_FILE:-$R/docker-compose.yml}"
DRY="${DRY_RUN:-0}"
log(){ printf '[homelab-mode] %s\n' "$*"; }
run(){ [[ "$DRY" == 1 ]] && log "[dry-run] $*" || { log "+ $*"; "$@"; }; }
ws(){ mkdir -p "$(dirname "$S")"; n=$(date +%s); printf '{"mode":"%s","updated_at":%s,"applied_at":%s,"message":"%s","details":{}}\n' "$1" "$n" "$n" "$2" >"$S"; }
core(){ [[ -f "$C" ]] && run docker compose -f "$C" up -d redis qdrant mqtt moltbot-api media-api; }
ollama_on(){ systemctl list-unit-files ollama.service &>/dev/null 2>&1 && run sudo systemctl start ollama || true; }
ollama_off(){ command -v ollama &>/dev/null && ollama ps -q 2>/dev/null | while read -r i; do [[ -n "$i" ]] && run ollama stop "$i"; done; systemctl is-active ollama &>/dev/null 2>&1 && run sudo systemctl stop ollama || true; }
case "${1:-status}" in
status) [[ -f "$S" ]] && cat "$S" || echo '{"mode":"unknown"}';;
apply) case "$2" in ai) ollama_on; core; ws ai applied;; gaming) ollama_off; ws gaming applied; log "steam -bigpicture";; media) ollama_on; core; ws media applied;; *) exit 1;; esac;;
sync) grep -q '"applied_at": null' "$S" 2>/dev/null && "$0" apply "$(grep -o '"mode":"[^"]*"' "$S" | head -1 | cut -d'"' -f4)" || true;;
*) echo "usage: $0 status|apply MODE|sync" >&2; exit 1;;
esac
