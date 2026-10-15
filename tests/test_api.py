"""Tests for the Cashlytics API client."""

from __future__ import annotations

from datetime import date

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.cashlytics.api import (
    CashlyticsApiError,
    CashlyticsAuthError,
    CashlyticsClient,
    CashlyticsConnectionError,
    CashlyticsNotSupportedError,
    CashlyticsRateLimitError,
    normalize_url,
)

from .conftest import HEALTH, TOKEN

BASE = "http://cashlytics.local:3000"


@pytest.fixture
async def client(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> CashlyticsClient:
    """Client against the mocked session (the mock must exist before the session)."""
    return CashlyticsClient(async_get_clientsession(hass), BASE + "/", TOKEN)


def test_normalize_url() -> None:
    """Scheme is added and trailing slashes removed."""
    assert normalize_url(" 192.168.1.10:3000/ ") == "http://192.168.1.10:3000"
    assert normalize_url("https://cashlytics.example.com/") == "https://cashlytics.example.com"


async def test_health_without_token(
    client: CashlyticsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """The health check is public and sends no token."""
    aioclient_mock.get(f"{BASE}/api/v1/health", json=HEALTH)
    assert await client.health() == HEALTH
    headers = aioclient_mock.mock_calls[0][3]
    assert "Authorization" not in headers


async def test_requests_send_token_and_params(
    client: CashlyticsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Data requests carry the bearer token and the query."""
    aioclient_mock.get(f"{BASE}/api/v1/payments", json={"payments": [{"id": "x"}]})
    assert await client.payments(date(2026, 10, 1), date(2026, 10, 31)) == [{"id": "x"}]
    _, url, _, headers = aioclient_mock.mock_calls[0]
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert url.query == {"start": "2026-10-01", "end": "2026-10-31"}


@pytest.mark.parametrize(
    ("status", "headers", "error"),
    [
        (401, None, CashlyticsAuthError),
        (302, {"Location": "/login"}, CashlyticsNotSupportedError),
        (404, None, CashlyticsNotSupportedError),
        (500, None, CashlyticsApiError),
    ],
)
async def test_error_status(
    client: CashlyticsClient,
    aioclient_mock: AiohttpClientMocker,
    status: int,
    headers: dict[str, str] | None,
    error: type[Exception],
) -> None:
    """HTTP errors map to client errors."""
    aioclient_mock.get(f"{BASE}/api/v1/me", status=status, headers=headers)
    with pytest.raises(error):
        await client.me()


async def test_rate_limit(client: CashlyticsClient, aioclient_mock: AiohttpClientMocker) -> None:
    """429 carries the server's Retry-After."""
    aioclient_mock.get(f"{BASE}/api/v1/me", status=429, headers={"Retry-After": "12"})
    with pytest.raises(CashlyticsRateLimitError) as err:
        await client.me()
    assert err.value.retry_after == 12


async def test_connection_error(
    client: CashlyticsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Network failures become connection errors."""
    aioclient_mock.get(f"{BASE}/api/v1/me", exc=TimeoutError)
    with pytest.raises(CashlyticsConnectionError):
        await client.me()


async def test_health_of_other_service(
    client: CashlyticsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A JSON endpoint that is not Cashlytics is rejected."""
    aioclient_mock.get(f"{BASE}/api/v1/health", json={"status": "healthy"})
    with pytest.raises(CashlyticsNotSupportedError):
        await client.health()
