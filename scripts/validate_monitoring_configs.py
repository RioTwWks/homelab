#!/usr/bin/env python3
"""Parse monitoring/ YAML and JSON (used by make check and CI)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MONITORING = ROOT / "monitoring"


def main() -> int:
    errors: list[str] = []
    for path in sorted(MONITORING.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
            if path.suffix in (".yml", ".yaml"):
                yaml.safe_load(text)
            elif path.suffix == ".json":
                json.loads(text)
        except Exception as exc:  # noqa: BLE001 — report all parse failures
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("monitoring YAML/JSON OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
