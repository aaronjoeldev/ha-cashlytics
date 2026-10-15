"""Sensors for Cashlytics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import CashlyticsConfigEntry, CashlyticsCoordinator, CashlyticsData
from .entity import CashlyticsAccountEntity, CashlyticsEntity

# Read-only platform; the coordinator fetches all data
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class CashlyticsSensorDescription(SensorEntityDescription):
    """Sensor of the overview device."""

    value_fn: Callable[[CashlyticsData], float | int | date | None]
    attributes_fn: Callable[[CashlyticsData], dict[str, Any]] | None = None
    # Amounts are in the user's base currency
    monetary: bool = False


def _month(data: CashlyticsData) -> dict[str, Any]:
    return data.summary["month"]


def _next_payment_date(data: CashlyticsData) -> date | None:
    payment = data.summary["upcoming"]["next"]
    return date.fromisoformat(payment["date"]) if payment else None


def _next_payment_attributes(data: CashlyticsData) -> dict[str, Any]:
    payment = data.summary["upcoming"]["next"]
    if not payment:
        return {}
    category = payment.get("category") or {}
    return {
        "name": payment["name"],
        "amount": payment["amount"],
        "currency": data.currency,
        "category": category.get("name"),
        "is_subscription": payment["isSubscription"],
    }


def _view_attributes(key: str) -> Callable[[CashlyticsData], dict[str, Any]]:
    """Reserve view value and month-over-month change of a cashflow figure."""

    def attributes(data: CashlyticsData) -> dict[str, Any]:
        month = _month(data)
        attrs: dict[str, Any] = {
            "year": month["year"],
            "month": month["month"],
            "reserve_view": month["reserve"][key],
        }
        if key != "surplus":
            attrs["change_pct"] = month["cashflow"][f"{key}ChangePct"]
        return attrs

    return attributes


OVERVIEW_SENSORS: tuple[CashlyticsSensorDescription, ...] = (
    CashlyticsSensorDescription(
        key="total_assets",
        translation_key="total_assets",
        monetary=True,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.summary["totalAssets"],
        attributes_fn=lambda data: {"has_multi_currency": data.summary["hasMultiCurrency"]},
    ),
    CashlyticsSensorDescription(
        key="month_income",
        translation_key="month_income",
        monetary=True,
        value_fn=lambda data: _month(data)["cashflow"]["income"],
        attributes_fn=_view_attributes("income"),
    ),
    CashlyticsSensorDescription(
        key="month_expenses",
        translation_key="month_expenses",
        monetary=True,
        value_fn=lambda data: _month(data)["cashflow"]["expenses"],
        attributes_fn=_view_attributes("expenses"),
    ),
    CashlyticsSensorDescription(
        key="month_surplus",
        translation_key="month_surplus",
        monetary=True,
        value_fn=lambda data: _month(data)["cashflow"]["surplus"],
        attributes_fn=_view_attributes("surplus"),
    ),
    CashlyticsSensorDescription(
        key="income_change",
        translation_key="income_change",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda data: _month(data)["cashflow"]["incomeChangePct"],
    ),
    CashlyticsSensorDescription(
        key="expenses_change",
        translation_key="expenses_change",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda data: _month(data)["cashflow"]["expensesChangePct"],
    ),
    CashlyticsSensorDescription(
        key="fixed_costs",
        translation_key="fixed_costs",
        monetary=True,
        value_fn=lambda data: data.summary["recurring"]["fixedCostsMonthly"],
        attributes_fn=lambda data: {"count": data.summary["recurring"]["fixedCostsCount"]},
    ),
    CashlyticsSensorDescription(
        key="subscriptions",
        translation_key="subscriptions",
        monetary=True,
        value_fn=lambda data: data.summary["recurring"]["subscriptionsMonthly"],
        attributes_fn=lambda data: {"count": data.summary["recurring"]["subscriptionsCount"]},
    ),
    CashlyticsSensorDescription(
        key="upcoming_payments",
        translation_key="upcoming_payments",
        monetary=True,
        value_fn=lambda data: data.summary["upcoming"]["total"],
        attributes_fn=lambda data: {
            "days": data.summary["upcoming"]["days"],
            "count": data.summary["upcoming"]["count"],
            "payments": [
                {
                    "date": payment["date"],
                    "name": payment["name"],
                    "amount": payment["amount"],
                    "is_subscription": payment["isSubscription"],
                }
                for payment in data.summary["upcoming"]["payments"]
            ],
        },
    ),
    CashlyticsSensorDescription(
        key="next_payment",
        translation_key="next_payment",
        device_class=SensorDeviceClass.DATE,
        value_fn=_next_payment_date,
        attributes_fn=_next_payment_attributes,
    ),
    CashlyticsSensorDescription(
        key="forecast_balance",
        translation_key="forecast_balance",
        monetary=True,
        value_fn=lambda data: data.summary["forecast"]["projectedBalance"],
        attributes_fn=lambda data: {
            "months": data.summary["forecast"]["months"],
            "projected_income": data.summary["forecast"]["projectedIncome"],
            "projected_expenses": data.summary["forecast"]["projectedExpenses"],
            "monthly": data.summary["forecast"]["monthly"],
        },
    ),
    CashlyticsSensorDescription(
        key="unread_insights",
        translation_key="unread_insights",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.summary["insights"]["unread"],
        attributes_fn=lambda data: {
            "by_severity": data.summary["insights"]["bySeverity"],
            "by_type": data.summary["insights"]["byType"],
        },
    ),
)


@dataclass(frozen=True, kw_only=True)
class CashlyticsAccountSensorDescription(SensorEntityDescription):
    """Sensor of an account device."""

    value_fn: Callable[[dict[str, Any]], float | None]
    attributes_fn: Callable[[dict[str, Any], CashlyticsData], dict[str, Any]] | None = None
    # Created only for accounts the function accepts
    exists_fn: Callable[[dict[str, Any]], bool] = lambda account: True
    # True: the amount is in the account's currency, False: in the base currency
    account_currency: bool = False


def _first_forecast_month(account: dict[str, Any]) -> dict[str, Any] | None:
    forecast = account.get("forecast") or {}
    monthly = forecast.get("monthly") or []
    return monthly[0] if monthly else None


ACCOUNT_SENSORS: tuple[CashlyticsAccountSensorDescription, ...] = (
    CashlyticsAccountSensorDescription(
        key="balance",
        translation_key="account_balance",
        account_currency=True,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda account: account["balance"],
        attributes_fn=lambda account, data: {
            "type": account["type"],
            "balance_in_base_currency": account["balanceInBaseCurrency"],
            "base_currency": data.currency,
        },
    ),
    CashlyticsAccountSensorDescription(
        key="forecast_balance",
        translation_key="account_forecast_balance",
        exists_fn=lambda account: bool((account.get("forecast") or {}).get("isCumulative")),
        value_fn=lambda account: (account.get("forecast") or {}).get("projectedBalance"),
        attributes_fn=lambda account, data: {
            "months": account["forecast"]["months"],
            "monthly": account["forecast"]["monthly"],
        },
    ),
    CashlyticsAccountSensorDescription(
        key="next_month_net",
        translation_key="account_next_month_net",
        value_fn=lambda account: (month := _first_forecast_month(account)) and month["net"],
        attributes_fn=lambda account, data: (
            {
                "year": month["year"],
                "month": month["month"],
                "income": month["income"],
                "expenses": month["expenses"],
                "transfers_in": month["transfersIn"],
                "transfers_out": month["transfersOut"],
            }
            if (month := _first_forecast_month(account))
            else {}
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CashlyticsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Cashlytics sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        CashlyticsSensor(coordinator, description) for description in OVERVIEW_SENSORS
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
            CashlyticsAccountSensor(coordinator, account_id, description)
            for account_id in new_ids
            for description in ACCOUNT_SENSORS
            if description.exists_fn(coordinator.data.accounts[account_id])
        )

    add_account_sensors()
    entry.async_on_unload(coordinator.async_add_listener(add_account_sensors))


class CashlyticsSensor(CashlyticsEntity, SensorEntity):
    """Sensor of the overview device."""

    entity_description: CashlyticsSensorDescription

    def __init__(
        self, coordinator: CashlyticsCoordinator, description: CashlyticsSensorDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        if description.monetary:
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | int | date | None:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Base currency for amounts."""
        if self.entity_description.monetary:
            return self.coordinator.data.currency
        return super().native_unit_of_measurement

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return details of the value."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)


class CashlyticsAccountSensor(CashlyticsAccountEntity, SensorEntity):
    """Sensor of an account device."""

    entity_description: CashlyticsAccountSensorDescription
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator: CashlyticsCoordinator,
        account_id: str,
        description: CashlyticsAccountSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, account_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        return self.entity_description.value_fn(self.account)

    @property
    def native_unit_of_measurement(self) -> str:
        """Account currency for the balance, base currency for projections."""
        if self.entity_description.account_currency:
            return self.account["currency"]
        return self.coordinator.data.currency

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return details of the value."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.account, self.coordinator.data)
