#!/usr/bin/env bash
set -euo pipefail
ROOT="${HOMELAB_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
DEST="$HOME/.hermes/skills/homelab"
mkdir -p "$HOME/.hermes/skills" "$DEST"
for d in "$ROOT/hermes/skills"/*/; do ln -sfn "${d%/}" "$DEST/$(basename "$d")"; done
mkdir -p "$HOME/.hermes"
[[ -f "$HOME/.hermes/config.yaml" ]] || cp "$ROOT/hermes/config/config.yaml.example" "$HOME/.hermes/config.yaml"
