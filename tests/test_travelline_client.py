import pytest

from errors import AuthenticationError, ExternalServiceError
from travelline_client import TravelLineClient, TravelLineConfig


class FakeResponse:
    """Подделка под httpx.Response для тестов — не ходит в сеть."""

    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


@pytest.fixture
def client():
    config = TravelLineConfig(
        client_id="test-id",
        client_secret="test-secret",
        property_id="prop-123",
        base_url="https://sandbox.example.com",
        auth_url="https://sandbox.example.com/auth/token",
    )
    return TravelLineClient(config)


async def test_get_access_token_success(monkeypatch, client):
    async def fake_post(self, url, data=None, **kwargs):
        return FakeResponse(200, {"access_token": "abc123", "expires_in": 3600})

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    token = await client._get_access_token()
    assert token == "abc123"


async def test_get_access_token_caches(monkeypatch, client):
    call_count = 0

    async def fake_post(self, url, data=None, **kwargs):
        nonlocal call_count
        call_count += 1
        return FakeResponse(200, {"access_token": "abc123", "expires_in": 3600})

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    await client._get_access_token()
    await client._get_access_token()
    assert call_count == 1  # второй раз токен взят из кэша


async def test_get_access_token_invalid_credentials(monkeypatch, client):
    async def fake_post(self, url, data=None, **kwargs):
        return FakeResponse(401)

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    with pytest.raises(AuthenticationError):
        await client._get_access_token()


async def test_search_room_stays_success(monkeypatch, client):
    async def fake_post(self, url, data=None, **kwargs):
        return FakeResponse(200, {"access_token": "abc123", "expires_in": 3600})

    async def fake_get(self, url, headers=None, params=None, **kwargs):
        return FakeResponse(200, {"roomStays": [{"roomType": "1270", "price": 4500}]})

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

    result = await client.search_room_stays("2026-07-20", "2026-07-23", 2)
    assert result == [{"roomType": "1270", "price": 4500}]


async def test_search_room_stays_rate_limited(monkeypatch, client):
    async def fake_post(self, url, data=None, **kwargs):
        return FakeResponse(200, {"access_token": "abc123", "expires_in": 3600})

    async def fake_get(self, url, headers=None, params=None, **kwargs):
        return FakeResponse(429)

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

    with pytest.raises(ExternalServiceError):
        await client.search_room_stays("2026-07-20", "2026-07-23", 2)