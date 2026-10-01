#!/usr/bin/env bash
set -euo pipefail
# See docs/hermes-voice-npu.md
command -v flm >/dev/null || { echo "Install: pip install fastflowlm" >&2; exit 127; }
exec flm validate "$@"
