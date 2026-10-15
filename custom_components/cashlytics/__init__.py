"""The Cashlytics integration."""

from __future__ import annotations

from homeassistant.const import CONF_API_TOKEN, CONF_URL, CONF_VERIFY_SSL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CashlyticsClient
from .const import ACCOUNT_DEVICE_PREFIX, DOMAIN
from .coordinator import CashlyticsConfigEntry, CashlyticsCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.CALENDAR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: CashlyticsConfigEntry) -> bool:
    """Set up Cashlytics from a config entry."""
    verify_ssl = entry.data.get(CONF_VERIFY_SSL, True)
    client = CashlyticsClient(
        async_get_clientsession(hass, verify_ssl=verify_ssl),
        entry.data[CONF_URL],
        entry.data[CONF_API_TOKEN],
        verify_ssl=verify_ssl,
    )
    coordinator = CashlyticsCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CashlyticsConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: CashlyticsConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow removing the device of an account that no longer exists in Cashlytics."""
    account_ids = entry.runtime_data.data.accounts.keys()
    for domain, identifier in device.identifiers:
        if domain != DOMAIN:
            continue
        if identifier == entry.unique_id:
            return False
        if identifier.startswith(ACCOUNT_DEVICE_PREFIX) and (
            identifier.removeprefix(ACCOUNT_DEVICE_PREFIX) in account_ids
        ):
            return False
    return True
