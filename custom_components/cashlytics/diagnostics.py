"""Diagnostics for Cashlytics."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant

from .coordinator import CashlyticsConfigEntry

# Account and payment names can identify people, employers or landlords
TO_REDACT = {CONF_API_TOKEN, CONF_URL, "name", "email", "title", "message", "unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: CashlyticsConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "options": {
            "update_interval": str(coordinator.update_interval),
            "forecast_months": coordinator.forecast_months,
            "upcoming_days": coordinator.upcoming_days,
        },
        "data": async_redact_data(asdict(coordinator.data), TO_REDACT),
    }
