from __future__ import annotations
import os, sys
from pathlib import Path

def repo_root() -> Path:
    if os.environ.get("HOMELAB_ROOT"):
        return Path(os.environ["HOMELAB_ROOT"]).expanduser().resolve()
    return Path(__file__).resolve().parents[2]

def init_runtime() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    root = repo_root()
    api = root / "moltbot_api"
    if not api.is_dir():
        raise SystemExit(f"moltbot_api missing under {root}")
    sys.path.insert(0, str(api))
    env = root / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
    os.environ.setdefault("MEDIA_API_BASE_URL", "http://127.0.0.1:8090")
    if not os.environ.get("SEARXNG_BASE_URL") or "searxng:" in os.environ.get("SEARXNG_BASE_URL", ""):
        os.environ.setdefault("SEARXNG_BASE_URL", "http://127.0.0.1:18081")
    if os.environ.get("HOME_ASSISTANT_URL"):
        os.environ["HOME_ASSISTANT_URL"] = os.environ["HOME_ASSISTANT_URL"].replace("host.docker.internal", "127.0.0.1")
