"""Tests for setup, entities and diagnostics of Cashlytics."""

from __future__ import annotations

import copy
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import (
    ClientSessionGenerator,
    WebSocketGenerator,
)

from custom_components.cashlytics.api import CashlyticsAuthError, CashlyticsConnectionError
from custom_components.cashlytics.const import DOMAIN

from .conftest import ACCOUNTS, CHECKING_ID, SAVINGS_ID, TOKEN, USER_ID, _account


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the entry and wait for its platforms."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture(autouse=True)
def frozen_today(freezer: FrozenDateTimeFactory) -> None:
    """Pin "today" to the date of the fixture payments."""
    freezer.move_to("2026-10-15 10:00:00+02:00")


async def test_setup_and_unload(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """The entry loads, creates its devices and unloads again."""
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED

    device_registry = dr.async_get(hass)
    assert device_registry.async_get_device({(DOMAIN, USER_ID)}).name == "Cashlytics (Demo User)"
    savings = device_registry.async_get_device({(DOMAIN, f"account_{SAVINGS_ID}")})
    assert savings.name == "Notgroschen"
    assert savings.model == "Savings account"

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_auth_failure_starts_reauth(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """A rejected token puts the entry into reauthentication."""
    mock_client.summary.side_effect = CashlyticsAuthError
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


async def test_setup_connection_failure_retries(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """An unreachable instance is retried later."""
    mock_client.accounts.side_effect = CashlyticsConnectionError
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_overview_sensors(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Overview sensors carry amounts in the base currency."""
    await setup_integration(hass, mock_config_entry)

    total = hass.states.get("sensor.cashlytics_demo_user_total_assets")
    assert total.state == "24496.05"
    assert total.attributes["unit_of_measurement"] == "EUR"
    assert total.attributes["device_class"] == "monetary"
    assert total.attributes["state_class"] == "total"

    expenses = hass.states.get("sensor.cashlytics_demo_user_expenses_this_month")
    assert expenses.state == "1663.28"
    assert expenses.attributes["reserve_view"] == 1663.28
    assert expenses.attributes["change_pct"] == -29.6

    next_payment = hass.states.get("sensor.cashlytics_demo_user_next_payment")
    assert next_payment.state == "2026-10-18"
    assert next_payment.attributes["name"] == "Miete"
    assert next_payment.attributes["amount"] == 850

    assert hass.states.get("sensor.cashlytics_demo_user_forecast_balance").state == "7460.16"
    assert hass.states.get("sensor.cashlytics_demo_user_unread_insights").state == "1"
    # Month-over-month changes are disabled by default
    assert hass.states.get("sensor.cashlytics_demo_user_income_vs_last_month") is None


async def test_account_sensors(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Accounts get a balance and, for savings, a forecast balance."""
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get("sensor.notgroschen_balance").state == "12500"
    assert hass.states.get("sensor.notgroschen_forecast_balance").state == "13400"
    assert hass.states.get("sensor.notgroschen_net_next_month").state == "300"
    assert hass.states.get("sensor.hauptkonto_balance").state == "3245.8"
    # Checking accounts have no running forecast balance
    assert hass.states.get("sensor.hauptkonto_forecast_balance") is None


async def test_binary_sensors(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Due payments ignore incomes; insights and the month drive the problem sensors."""
    await setup_integration(hass, mock_config_entry)

    today = hass.states.get("binary_sensor.cashlytics_demo_user_payment_due_today")
    assert today.state == STATE_ON
    assert today.attributes["payments"] == [{"name": "Bäcker", "amount": 8.5}]
    # Only the salary is due tomorrow
    assert (
        hass.states.get("binary_sensor.cashlytics_demo_user_payment_due_tomorrow").state
        == STATE_OFF
    )
    assert hass.states.get("binary_sensor.cashlytics_demo_user_spending_anomaly").state == STATE_ON
    assert hass.states.get("binary_sensor.cashlytics_demo_user_budget_warning").state == STATE_OFF
    assert (
        hass.states.get("binary_sensor.cashlytics_demo_user_deficit_this_month").state == STATE_OFF
    )
    assert hass.states.get("binary_sensor.hauptkonto_negative_balance").state == STATE_OFF


async def test_accounts_added_and_removed(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """New accounts get entities on the next poll; deleted ones become unavailable."""
    await setup_integration(hass, mock_config_entry)

    etf_id = "a0000000-0000-0000-0000-000000000003"
    mock_client.accounts.return_value = [
        copy.deepcopy(ACCOUNTS[0]),
        _account(etf_id, "Weltportfolio", "etf", 8750.25),
    ]
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("sensor.weltportfolio_balance").state == "8750.25"
    assert hass.states.get("sensor.notgroschen_balance").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.hauptkonto_balance").state == "3245.8"


async def test_remove_stale_account_device(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Only devices of deleted accounts can be removed."""
    assert await async_setup_component(hass, "config", {})
    await setup_integration(hass, mock_config_entry)
    device_registry = dr.async_get(hass)
    checking = device_registry.async_get_device({(DOMAIN, f"account_{CHECKING_ID}")})
    stale = device_registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={(DOMAIN, "account_deleted")},
    )

    client = await hass_ws_client(hass)
    for device, removable in ((checking, False), (stale, True)):
        await client.send_json_auto_id(
            {
                "type": "config/device_registry/remove_config_entry",
                "config_entry_id": mock_config_entry.entry_id,
                "device_id": device.id,
            }
        )
        response = await client.receive_json()
        assert response["success"] is removable


async def test_calendar(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """The calendar shows the next due date and fetches ranges from the API."""
    await setup_integration(hass, mock_config_entry)

    calendar = hass.states.get("calendar.cashlytics_demo_user_payments")
    assert calendar.attributes["message"] == "Bäcker -8.50 EUR"
    assert calendar.attributes["all_day"] is True

    response = await hass.services.async_call(
        "calendar",
        "get_events",
        {"start_date_time": "2026-10-01T00:00:00", "end_date_time": "2027-12-01T00:00:00"},
        target={"entity_id": "calendar.cashlytics_demo_user_payments"},
        blocking=True,
        return_response=True,
    )
    events = response["calendar.cashlytics_demo_user_payments"]["events"]
    # The range is longer than the API allows in one request, so it is split
    assert mock_client.payments.await_count >= 3
    assert {"start": "2026-10-16", "end": "2026-10-17", "summary": "Gehalt +3200.00 EUR"} in [
        {key: event[key] for key in ("start", "end", "summary")} for event in events
    ]


async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Diagnostics hide the token, the URL and names."""
    await setup_integration(hass, mock_config_entry)
    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, mock_config_entry)
    text = str(diagnostics)
    assert TOKEN not in text
    assert "cashlytics.local" not in text
    assert "Notgroschen" not in text
    assert "Miete" not in text
    assert diagnostics["data"]["summary"]["totalAssets"] == 24496.05


async def test_entity_unique_ids(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Unique ids are derived from the user and account ids."""
    await setup_integration(hass, mock_config_entry)
    entity_registry = er.async_get(hass)
    entry = entity_registry.async_get("sensor.notgroschen_balance")
    assert entry.unique_id == f"{USER_ID}_{SAVINGS_ID}_balance"
