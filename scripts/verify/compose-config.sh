#!/usr/bin/env bash
# Validate docker-compose.yml (base + optional profiles + raid overlays).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose -f docker-compose.yml)

run_config() {
  local label="$1"
  shift
  echo "==> compose config: ${label}"
  "${COMPOSE[@]}" "$@" config --quiet
}

run_config "default"
run_config "profile ui" --profile ui
run_config "profile monitoring" --profile monitoring
run_config "profile search" --profile search
run_config "profile voice" --profile voice

run_config "raid example overlay" -f docker-compose.raid.example.yml
run_config "raid-full example overlay" -f docker-compose.raid-full.example.yml

echo "OK: docker compose config (default, ui, monitoring, search, voice, raid overlays)"
