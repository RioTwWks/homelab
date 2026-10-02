#!/usr/bin/env bash
# Copy homelab Hermes personality SOUL templates into ~/.hermes/personalities/
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT}/hermes/personalities"
DEST="${HERMES_HOME:-$HOME/.hermes}/personalities"

if [[ ! -d "$SRC" ]]; then
  echo "Missing source: $SRC" >&2
  exit 1
fi

mkdir -p "$DEST"
for profile in child student adult; do
  if [[ -d "$SRC/$profile" ]]; then
    mkdir -p "$DEST/$profile"
    install -m 0644 "$SRC/$profile/SOUL.md" "$DEST/$profile/SOUL.md"
    echo "Installed $profile → $DEST/$profile/SOUL.md"
  fi
done

echo "Done. Activate with Hermes CLI: /personality child|student|adult (after registering in config)."
echo "Or symlink active SOUL: ln -sf \"$DEST/adult/SOUL.md\" \"${HERMES_HOME:-$HOME/.hermes}/SOUL.md\""
