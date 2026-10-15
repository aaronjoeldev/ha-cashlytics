"""Binary sensors for Cashlytics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import CashlyticsConfigEntry, CashlyticsCoordinator, CashlyticsData
from .entity import CashlyticsAccountEntity, CashlyticsEntity

PARALLEL_UPDATES = 0


def _outgoing_on(data: CashlyticsData, day: date) -> list[dict[str, Any]]:
    """Expenses and daily expenses due on a day (incomes are not payments)."""
    iso_day = day.isoformat()
    return [
        payment
        for payment in data.payments
        if payment["date"] == iso_day and payment["type"] != "income"
    ]


def _due_attributes(data: CashlyticsData, day: date) -> dict[str, Any]:
    payments = _outgoing_on(data, day)
    return {
        "count": len(payments),
        "total": round(sum(payment["amount"] for payment in payments), 2),
        "currency": data.currency,
        "payments": [
            {"name": payment["name"], "amount": payment["amount"]} for payment in payments
        ],
    }


def _today() -> date:
    return dt_util.now().date()


def _insight_count(data: CashlyticsData, insight_type: str) -> int:
    return data.summary["insights"]["byType"].get(insight_type, 0)


@dataclass(frozen=True, kw_only=True)
class CashlyticsBinarySensorDescription(BinarySensorEntityDescription):
    """Binary sensor of the overview device."""

    is_on_fn: Callable[[CashlyticsData], bool]
    attributes_fn: Callable[[CashlyticsData], dict[str, Any]] | None = None


OVERVIEW_BINARY_SENSORS: tuple[CashlyticsBinarySensorDescription, ...] = (
    CashlyticsBinarySensorDescription(
        key="payment_due_today",
        translation_key="payment_due_today",
        is_on_fn=lambda data: bool(_outgoing_on(data, _today())),
        attributes_fn=lambda data: _due_attributes(data, _today()),
    ),
    CashlyticsBinarySensorDescription(
        key="payment_due_tomorrow",
        translation_key="payment_due_tomorrow",
        is_on_fn=lambda data: bool(_outgoing_on(data, _today() + timedelta(days=1))),
        attributes_fn=lambda data: _due_attributes(data, _today() + timedelta(days=1)),
    ),
    CashlyticsBinarySensorDescription(
        key="month_deficit",
        translation_key="month_deficit",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda data: data.summary["month"]["cashflow"]["surplus"] < 0,
    ),
    CashlyticsBinarySensorDescription(
        key="spending_anomaly",
        translation_key="spending_anomaly",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda data: _insight_count(data, "spending_anomaly") > 0,
    ),
    CashlyticsBinarySensorDescription(
        key="budget_warning",
        translation_key="budget_warning",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda data: _insight_count(data, "budget_warning") > 0,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CashlyticsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Cashlytics binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        CashlyticsBinarySensor(coordinator, description) for description in OVERVIEW_BINARY_SENSORS
    )

    known_accounts: set[str] = set()

    @callback
    def add_account_sensors() -> None:
        """Add sensors for accounts that appeared since the last poll."""
        new_ids = coordinator.data.accounts.keys() - known_accounts
        if not new_ids:
            return
        known_accounts.update(new_ids)
        async_add_entities(
            CashlyticsNegativeBalanceSensor(coordinator, account_id) for account_id in new_ids
        )

    add_account_sensors()
    entry.async_on_unload(coordinator.async_add_listener(add_account_sensors))


class CashlyticsBinarySensor(CashlyticsEntity, BinarySensorEntity):
    """Binary sensor of the overview device."""

    entity_description: CashlyticsBinarySensorDescription

    def __init__(
        self,
        coordinator: CashlyticsCoordinator,
        description: CashlyticsBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return self.entity_description.is_on_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return details of the state."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)


class CashlyticsNegativeBalanceSensor(CashlyticsAccountEntity, BinarySensorEntity):
    """On while the balance of an account is below zero."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "negative_balance"

    def __init__(self, coordinator: CashlyticsCoordinator, account_id: str) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, account_id, "negative_balance")

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return self.account["balance"] < 0
