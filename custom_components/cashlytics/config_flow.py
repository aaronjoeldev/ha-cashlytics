"""Config flow for Cashlytics."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_API_TOKEN, CONF_SCAN_INTERVAL, CONF_URL, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .api import (
    CashlyticsAuthError,
    CashlyticsClient,
    CashlyticsConnectionError,
    CashlyticsError,
    CashlyticsNotSupportedError,
    normalize_url,
)
from .const import (
    CONF_FORECAST_MONTHS,
    CONF_UPCOMING_DAYS,
    DEFAULT_FORECAST_MONTHS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UPCOMING_DAYS,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
    SUPPORTED_API_VERSION,
)
from .coordinator import CashlyticsConfigEntry

_LOGGER = logging.getLogger(__name__)

TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
URL_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.URL))


class UnsupportedVersion(CashlyticsError):
    """The instance speaks another API version."""


async def validate_connection(
    hass: HomeAssistant, url: str, token: str, verify_ssl: bool
) -> dict[str, Any]:
    """Check the instance and the token; return the token owner (/api/v1/me)."""
    client = CashlyticsClient(
        async_get_clientsession(hass, verify_ssl=verify_ssl), url, token, verify_ssl=verify_ssl
    )
    health = await client.health()
    if health["apiVersion"] != SUPPORTED_API_VERSION:
        raise UnsupportedVersion(f"API version {health['apiVersion']}")
    return await client.me()


def _errors_for(err: Exception) -> dict[str, str]:
    if isinstance(err, CashlyticsAuthError):
        return {"base": "invalid_auth"}
    if isinstance(err, CashlyticsConnectionError):
        return {"base": "cannot_connect"}
    if isinstance(err, (CashlyticsNotSupportedError, UnsupportedVersion)):
        return {"base": "not_supported"}
    return {"base": "unknown"}


def _entry_title(me: dict[str, Any]) -> str:
    return f"Cashlytics ({me.get('name') or me.get('email') or me['userId']})"


class CashlyticsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cashlytics."""

    VERSION = 1
    MINOR_VERSION = 1

    async def _try_connect(
        self, url: str, token: str, verify_ssl: bool
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        try:
            me = await validate_connection(self.hass, url, token, verify_ssl)
        except CashlyticsError as err:
            _LOGGER.debug("Connecting to Cashlytics at %s failed: %s", url, err)
            return None, _errors_for(err)
        except Exception:
            _LOGGER.exception("Unexpected error connecting to Cashlytics")
            return None, {"base": "unknown"}
        return me, {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the instance URL and an API token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            url = normalize_url(user_input[CONF_URL])
            me, errors = await self._try_connect(
                url, user_input[CONF_API_TOKEN], user_input[CONF_VERIFY_SSL]
            )
            if me is not None:
                await self.async_set_unique_id(me["userId"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=_entry_title(me), data={**user_input, CONF_URL: url}
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_URL): URL_SELECTOR,
                        vol.Required(CONF_API_TOKEN): TOKEN_SELECTOR,
                        vol.Required(CONF_VERIFY_SSL, default=True): bool,
                    }
                ),
                user_input,
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start reauthentication after the token was rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new API token."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            me, errors = await self._try_connect(
                entry.data[CONF_URL],
                user_input[CONF_API_TOKEN],
                entry.data.get(CONF_VERIFY_SSL, True),
            )
            if me is not None:
                await self.async_set_unique_id(me["userId"])
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_TOKEN: user_input[CONF_API_TOKEN]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_TOKEN): TOKEN_SELECTOR}),
            description_placeholders={"url": entry.data[CONF_URL]},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change URL, token or certificate check of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            url = normalize_url(user_input[CONF_URL])
            me, errors = await self._try_connect(
                url, user_input[CONF_API_TOKEN], user_input[CONF_VERIFY_SSL]
            )
            if me is not None:
                await self.async_set_unique_id(me["userId"])
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry, data_updates={**user_input, CONF_URL: url}
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_URL): URL_SELECTOR,
                        vol.Required(CONF_API_TOKEN): TOKEN_SELECTOR,
                        vol.Required(CONF_VERIFY_SSL): bool,
                    }
                ),
                user_input or entry.data,
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: CashlyticsConfigEntry) -> CashlyticsOptionsFlow:
        """Create the options flow."""
        return CashlyticsOptionsFlow()


class CashlyticsOptionsFlow(OptionsFlowWithReload):
    """Polling interval and the windows of upcoming payments and forecast."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={key: int(value) for key, value in user_input.items()}
            )

        def number(minimum: int, maximum: int, unit: str) -> NumberSelector:
            return NumberSelector(
                NumberSelectorConfig(
                    min=minimum,
                    max=maximum,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement=unit,
                )
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=int(DEFAULT_SCAN_INTERVAL.total_seconds() // 60),
                ): number(MIN_SCAN_INTERVAL_MINUTES, MAX_SCAN_INTERVAL_MINUTES, "min"),
                vol.Required(CONF_UPCOMING_DAYS, default=DEFAULT_UPCOMING_DAYS): number(2, 90, "d"),
                vol.Required(CONF_FORECAST_MONTHS, default=DEFAULT_FORECAST_MONTHS): number(
                    1, 24, "mo"
                ),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, self.config_entry.options),
        )
