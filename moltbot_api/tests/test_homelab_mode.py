from pathlib import Path
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)

def test_get(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMELAB_MODE_STATE_PATH", str(tmp_path/"s.json"))
    assert client.get("/v1/system/homelab-mode").status_code == 200

def test_post(tmp_path, monkeypatch):
    sf = tmp_path/"s.json"
    monkeypatch.setenv("HOMELAB_MODE_STATE_PATH", str(sf))
    with patch("app.homelab_mode.request_mode_on_host", new_callable=AsyncMock) as m:
        m.return_value = {"skipped": True}
        assert client.post("/v1/system/homelab-mode", json={"mode": "gaming"}).status_code == 200
    assert sf.is_file()

def test_invalid():
    assert client.post("/v1/system/homelab-mode", json={"mode": "x"}).status_code == 422
