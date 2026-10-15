"""Minimal async client for the Cashlytics REST API (/api/v1)."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

import aiohttp
from yarl import URL

REQUEST_TIMEOUT = 30


class CashlyticsError(Exception):
    """Base error of the Cashlytics client."""


class CashlyticsConnectionError(CashlyticsError):
    """The instance could not be reached."""


class CashlyticsAuthError(CashlyticsError):
    """The API token is missing, invalid, expired or revoked."""


class CashlyticsNotSupportedError(CashlyticsError):
    """The URL does not serve a compatible Cashlytics REST API."""


class CashlyticsRateLimitError(CashlyticsError):
    """Too many requests; retry after `retry_after` seconds."""

    def __init__(self, retry_after: int | None) -> None:
        """Store the server's Retry-After value."""
        super().__init__("Rate limited by Cashlytics")
        self.retry_after = retry_after


class CashlyticsApiError(CashlyticsError):
    """Unexpected response from the API."""


def normalize_url(url: str) -> str:
    """Return the instance URL without trailing slash; add http:// when no scheme is given."""
    url = url.strip()
    if "://" not in url:
        url = f"http://{url}"
    return url.rstrip("/")


class CashlyticsClient:
    """Reads data from one Cashlytics instance with a personal API token."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        token: str,
        *,
        verify_ssl: bool = True,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._base = URL(normalize_url(base_url))
        self._token = token
        self._verify_ssl = verify_ssl

    async def _get(
        self, path: str, params: dict[str, Any] | None = None, *, auth: bool = True
    ) -> dict[str, Any]:
        url = self._base / "api" / "v1" / path
        headers = {"Accept": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self._session.get(
                    url,
                    params=params,
                    headers=headers,
                    # Older Cashlytics versions redirect unknown API routes to /login
                    allow_redirects=False,
                    ssl=None if self._verify_ssl else False,
                )
                async with response:
                    if response.status == 401:
                        raise CashlyticsAuthError("API token rejected")
                    if response.status == 429:
                        retry_after = response.headers.get("Retry-After")
                        raise CashlyticsRateLimitError(
                            int(retry_after) if retry_after and retry_after.isdigit() else None
                        )
                    if response.status in (301, 302, 303, 307, 308, 404):
                        raise CashlyticsNotSupportedError(
                            f"{url} is not available (HTTP {response.status})"
                        )
                    if response.status >= 400:
                        raise CashlyticsApiError(f"HTTP {response.status} from {url}")
                    try:
                        data = await response.json()
                    except (aiohttp.ContentTypeError, ValueError) as err:
                        raise CashlyticsNotSupportedError(f"{url} did not return JSON") from err
        except TimeoutError as err:
            raise CashlyticsConnectionError(f"Timeout connecting to {self._base}") from err
        except aiohttp.ClientError as err:
            raise CashlyticsConnectionError(f"Error connecting to {self._base}: {err}") from err

        if not isinstance(data, dict):
            raise CashlyticsApiError(f"Unexpected response from {url}")
        return data

    async def health(self) -> dict[str, Any]:
        """Return status, app version and API version; needs no token."""
        data = await self._get("health", auth=False)
        if data.get("status") != "ok" or "apiVersion" not in data:
            raise CashlyticsNotSupportedError("Not a Cashlytics health response")
        return data

    async def me(self) -> dict[str, Any]:
        """Return the token owner."""
        return await self._get("me")

    async def summary(self, *, upcoming_days: int, forecast_months: int) -> dict[str, Any]:
        """Return the aggregated figures of the dashboard."""
        return await self._get(
            "summary", {"upcomingDays": upcoming_days, "forecastMonths": forecast_months}
        )

    async def accounts(self, *, forecast_months: int) -> list[dict[str, Any]]:
        """Return all accounts with their forecast."""
        data = await self._get("accounts", {"forecastMonths": forecast_months})
        return data.get("accounts", [])

    async def payments(self, start: date, end: date) -> list[dict[str, Any]]:
        """Return all due dates between two days (inclusive, at most 366 days)."""
        data = await self._get("payments", {"start": start.isoformat(), "end": end.isoformat()})
        return data.get("payments", [])

    async def insights(self) -> list[dict[str, Any]]:
        """Return unread insights."""
        data = await self._get("insights")
        return data.get("insights", [])
