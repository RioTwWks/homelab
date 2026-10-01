import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "moltbot_api"))
sys.path.insert(0, str(ROOT / "hermes" / "tools"))
os.environ.setdefault("HOMELAB_ROOT", str(ROOT))

def test_media():
    from app.tools.media_control import parse_media_command
    assert parse_media_command("пауза")["action"] == "pause"

def test_ha():
    from app.tools.home_assistant import parse_ha_command
    assert parse_ha_command("включи свет в гостиная")["action"] == "turn_on"

def test_timer():
    from app.tools.timers import parse_timer_request
    assert parse_timer_request("поставь таймер на 5 минут")["duration_seconds"] == 300

def test_runtime():
    from _runtime import init_runtime, repo_root
    init_runtime()
    assert (repo_root() / "moltbot_api").is_dir()
