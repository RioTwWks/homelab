from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert isinstance(body["ts"], int)


def test_root() -> None:
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "media-api"
    assert body["ok"] is True


def test_command_without_executor() -> None:
    response = client.post(
        "/v1/command",
        json={"action": "open_url", "url": "https://example.com", "target": "browser"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["received"]["action"] == "open_url"
    assert body["received"]["url"] == "https://example.com"


def test_last_command() -> None:
    client.post(
        "/v1/command",
        json={"action": "pause", "target": "browser"},
    )
    response = client.get("/v1/command/last")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["last"]["action"] == "pause"
