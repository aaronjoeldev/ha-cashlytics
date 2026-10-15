"""Base entities for Cashlytics."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_URL
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import normalize_url
from .const import ACCOUNT_DEVICE_PREFIX, DOMAIN, MANUFACTURER
from .coordinator import CashlyticsCoordinator

ACCOUNT_MODELS = {"checking": "Checking account", "savings": "Savings account", "etf": "ETF"}


class CashlyticsEntity(CoordinatorEntity[CashlyticsCoordinator]):
    """Entity of the user's overview device (one per config entry)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CashlyticsCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model="Overview",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=normalize_url(entry.data[CONF_URL]),
        )


class CashlyticsAccountEntity(CoordinatorEntity[CashlyticsCoordinator]):
    """Entity of one Cashlytics account, grouped in a device per account."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CashlyticsCoordinator, account_id: str, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self.account_id = account_id
        # Kept so state and unit stay computable after the account is deleted (then unavailable)
        self._last_account: dict[str, Any] = coordinator.data.accounts[account_id]
        account = self._last_account
        self._attr_unique_id = f"{entry.unique_id}_{account_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{ACCOUNT_DEVICE_PREFIX}{account_id}")},
            name=account["name"],
            manufacturer=MANUFACTURER,
            model=ACCOUNT_MODELS.get(account["type"], account["type"]),
            entry_type=DeviceEntryType.SERVICE,
            via_device=(DOMAIN, entry.unique_id),
            configuration_url=f"{normalize_url(entry.data[CONF_URL])}/accounts/{account_id}",
        )

    @property
    def account(self) -> dict[str, Any]:
        """The account in the latest poll, or its last known state once deleted."""
        if (account := self.coordinator.data.accounts.get(self.account_id)) is not None:
            self._last_account = account
        return self._last_account

    @property
    def available(self) -> bool:
        """Unavailable once the account was deleted in Cashlytics."""
        return super().available and self.account_id in self.coordinator.data.accounts
