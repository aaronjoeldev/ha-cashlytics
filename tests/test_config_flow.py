"""Tests for the Cashlytics config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_TOKEN, CONF_SCAN_INTERVAL, CONF_URL, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cashlytics.api import (
    CashlyticsAuthError,
    CashlyticsConnectionError,
    CashlyticsNotSupportedError,
)
from custom_components.cashlytics.const import (
    CONF_FORECAST_MONTHS,
    CONF_UPCOMING_DAYS,
    DOMAIN,
)

from .conftest import TOKEN, USER_ID

USER_INPUT = {CONF_URL: "cashlytics.local:3000/", CONF_API_TOKEN: TOKEN, CONF_VERIFY_SSL: True}


async def test_user_flow(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """A valid URL and token create an entry keyed by the Cashlytics user."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Cashlytics (Demo User)"
    assert result["result"].unique_id == USER_ID
    assert result["data"] == {
        CONF_URL: "http://cashlytics.local:3000",
        CONF_API_TOKEN: TOKEN,
        CONF_VERIFY_SSL: True,
    }


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (CashlyticsAuthError, "invalid_auth"),
        (CashlyticsConnectionError, "cannot_connect"),
        (CashlyticsNotSupportedError, "not_supported"),
        (RuntimeError, "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant, mock_client: AsyncMock, side_effect: type[Exception], error: str
) -> None:
    """Errors are shown on the form and the flow recovers."""
    mock_client.me.side_effect = side_effect
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_client.me.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_unsupported_api_version(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    """A newer, incompatible API version is rejected."""
    mock_client.health.return_value = {"status": "ok", "version": "2.0.0", "apiVersion": 2}
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "not_supported"}


async def test_user_flow_already_configured(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """The same Cashlytics user cannot be added twice."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """A new token replaces the rejected one."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    new_token = "csk_" + "b" * 64
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_TOKEN: new_token}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_API_TOKEN] == new_token


async def test_reauth_flow_wrong_account(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """A token of another user does not replace the token of this entry."""
    mock_config_entry.add_to_hass(hass)
    mock_client.me.return_value = {**mock_client.me.return_value, "userId": "someone-else"}
    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_TOKEN: "csk_" + "c" * 64}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert mock_config_entry.data[CONF_API_TOKEN] == TOKEN


async def test_reconfigure_flow(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """URL and certificate check can be changed."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: "https://money.example.com", CONF_API_TOKEN: TOKEN, CONF_VERIFY_SSL: False},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_URL] == "https://money.example.com"
    assert mock_config_entry.data[CONF_VERIFY_SSL] is False


async def test_options_flow(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Options are stored as integers and passed to the API."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_INTERVAL: 30.0, CONF_UPCOMING_DAYS: 14.0, CONF_FORECAST_MONTHS: 6.0},
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == {
        CONF_SCAN_INTERVAL: 30,
        CONF_UPCOMING_DAYS: 14,
        CONF_FORECAST_MONTHS: 6,
    }
    mock_client.summary.assert_called_with(upcoming_days=14, forecast_months=6)
