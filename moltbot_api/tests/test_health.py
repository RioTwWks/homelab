from unittest.mock import AsyncMock, MagicMock, patch

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
    assert body["name"] == "moltbot-api"
    assert body["ok"] is True
    assert "healthz" in body["paths"]["health"]


@patch("app.main.RedisCache")
def test_system_status_without_external_services(mock_redis_cache: MagicMock) -> None:
    mock_instance = MagicMock()
    mock_instance.client.ping.return_value = True
    mock_redis_cache.from_env.return_value = mock_instance

    response = client.get("/v1/system/status")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["services"]["redis"] == "ok"


@patch("app.main.httpx.AsyncClient")
@patch("app.main.RedisCache")
def test_probe_services_with_url(
    mock_redis_cache: MagicMock,
    mock_async_client_cls: MagicMock,
) -> None:
    mock_instance = MagicMock()
    mock_instance.client.ping.return_value = True
    mock_redis_cache.from_env.return_value = mock_instance

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_async_client_cls.return_value = mock_client

    response = client.post(
        "/v1/system/services",
        json=[{"name": "example", "url": "http://example.com/healthz"}],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["services"]["example"] == "ok"
