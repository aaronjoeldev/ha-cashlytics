"""Data update coordinator for Cashlytics."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    CashlyticsAuthError,
    CashlyticsClient,
    CashlyticsError,
    CashlyticsRateLimitError,
)
from .const import (
    CALENDAR_LOOKAHEAD_DAYS,
    CONF_FORECAST_MONTHS,
    CONF_UPCOMING_DAYS,
    DEFAULT_FORECAST_MONTHS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UPCOMING_DAYS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

type CashlyticsConfigEntry = ConfigEntry[CashlyticsCoordinator]


@dataclass
class CashlyticsData:
    """One poll of the Cashlytics API."""

    summary: dict[str, Any]
    accounts: dict[str, dict[str, Any]]
    # Due dates from today on, for the calendar's current event
    payments: list[dict[str, Any]] = field(default_factory=list)

    @property
    def currency(self) -> str:
        """Base currency of the user."""
        return self.summary["currency"]


class CashlyticsCoordinator(DataUpdateCoordinator[CashlyticsData]):
    """Polls summary, accounts and the next scheduled payments in one cycle."""

    config_entry: CashlyticsConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CashlyticsConfigEntry,
        client: CashlyticsClient,
    ) -> None:
        """Initialize the coordinator."""
        scan_minutes = entry.options.get(CONF_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=(
                timedelta(minutes=scan_minutes) if scan_minutes else DEFAULT_SCAN_INTERVAL
            ),
        )
        self.client = client
        self.forecast_months: int = entry.options.get(CONF_FORECAST_MONTHS, DEFAULT_FORECAST_MONTHS)
        self.upcoming_days: int = entry.options.get(CONF_UPCOMING_DAYS, DEFAULT_UPCOMING_DAYS)

    async def _async_update_data(self) -> CashlyticsData:
        today = dt_util.now().date()
        try:
            summary, accounts, payments = await asyncio.gather(
                self.client.summary(
                    upcoming_days=self.upcoming_days, forecast_months=self.forecast_months
                ),
                self.client.accounts(forecast_months=self.forecast_months),
                self.client.payments(today, today + timedelta(days=CALENDAR_LOOKAHEAD_DAYS)),
            )
        except CashlyticsAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except CashlyticsRateLimitError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="rate_limited",
                retry_after=err.retry_after,
            ) from err
        except CashlyticsError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        return CashlyticsData(
            summary=summary,
            accounts={account["id"]: account for account in accounts},
            payments=payments,
        )
