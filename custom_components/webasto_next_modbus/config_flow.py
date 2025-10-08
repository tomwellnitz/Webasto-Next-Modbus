"""Config and options flow for the Webasto Next Modbus integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

try:
    import voluptuous as vol
except ModuleNotFoundError:  # pragma: no cover - handled at runtime
    vol = None
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .const import (
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_UNIT_ID,
    CONF_VARIANT,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DEFAULT_VARIANT,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    VARIANT_LABELS,
)
from .hub import ModbusBridge, WebastoModbusError

_LOGGER = logging.getLogger(__name__)


class WebastoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Webasto Next Modbus config flow."""

    VERSION = 1

    _host: str | None = None
    _unit_id: int | None = None

    async def async_step_user(
        self, user_input: Mapping[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial configuration step."""

        if vol is None:
            _LOGGER.error(
                "Missing dependency 'voluptuous'; aborting config flow. "
                "Please ensure the Home Assistant environment includes this package."
            )
            return self.async_abort(reason="missing_dependency")

        errors: dict[str, str] = {}

        normalized_input: dict[str, Any] | None = None

        if user_input is not None:
            normalized_input = _normalize_config_entry(user_input)
            try:
                await self._async_validate_and_connect(normalized_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except TimeoutError:
                errors["base"] = "cannot_connect"
            except Exception as err:  # pragma: no cover - defensive
                errors["base"] = "unknown"
                _LOGGER.exception("Unexpected error validating config: %s", err)
            else:
                assert normalized_input is not None
                await self.async_set_unique_id(
                    _build_unique_id(normalized_input[CONF_HOST], normalized_input[CONF_UNIT_ID])
                )
                self._abort_if_unique_id_configured()

                name = normalized_input.get(CONF_NAME, "")

                data = {
                    CONF_HOST: normalized_input[CONF_HOST],
                    CONF_PORT: normalized_input[CONF_PORT],
                    CONF_UNIT_ID: normalized_input[CONF_UNIT_ID],
                    CONF_SCAN_INTERVAL: normalized_input[CONF_SCAN_INTERVAL],
                    CONF_VARIANT: normalized_input[CONF_VARIANT],
                }
                if name:
                    data[CONF_NAME] = name

                host = normalized_input[CONF_HOST]
                unit_id = normalized_input[CONF_UNIT_ID]
                title = name or f"{host} (unit {unit_id})"

                return self.async_create_entry(
                    title=title,
                    data=data,
                    options={
                        CONF_SCAN_INTERVAL: normalized_input[CONF_SCAN_INTERVAL],
                        CONF_VARIANT: normalized_input[CONF_VARIANT],
                    },
                )

        defaults = normalized_input or {}

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): vol.All(
                    str,
                    vol.Length(min=1),
                ),
                vol.Required(
                    CONF_PORT,
                    default=defaults.get(CONF_PORT, DEFAULT_PORT),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=1, max=65535),
                ),
                vol.Required(
                    CONF_UNIT_ID,
                    default=defaults.get(CONF_UNIT_ID, DEFAULT_UNIT_ID),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=255,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_VARIANT,
                    default=defaults.get(CONF_VARIANT, DEFAULT_VARIANT),
                ): vol.In(VARIANT_LABELS),
                vol.Optional(CONF_NAME, default=defaults.get(CONF_NAME, "")): vol.All(
                    str,
                    vol.Length(max=100),
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)

    async def _async_validate_and_connect(self, data: Mapping[str, Any]) -> None:
        """Validate user input by performing a Modbus test read."""

        bridge = ModbusBridge(
            host=data[CONF_HOST],
            port=int(data[CONF_PORT]),
            unit_id=int(data[CONF_UNIT_ID]),
        )

        try:
            await bridge.async_connect()
            await bridge.async_test_connection()
        except WebastoModbusError as err:
            raise CannotConnect from err
        finally:
            await bridge.async_close()

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler."""

        return WebastoOptionsFlow(config_entry)


class WebastoOptionsFlow(config_entries.OptionsFlow):
    """Handle Webasto Next options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: Mapping[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options."""

        if vol is None:
            _LOGGER.error(
                "Missing dependency 'voluptuous'; aborting options flow. "
                "Please ensure the Home Assistant environment includes this package."
            )
            return self.async_abort(reason="missing_dependency")

        errors: dict[str, str] = {}
        current_interval = self._config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self._config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        current_variant = self._config_entry.options.get(
            CONF_VARIANT,
            self._config_entry.data.get(CONF_VARIANT, DEFAULT_VARIANT),
        )
        current_name = self._config_entry.data.get(CONF_NAME, "")

        if user_input is not None:
            interval = int(user_input[CONF_SCAN_INTERVAL])
            variant = user_input[CONF_VARIANT]
            name = str(user_input.get(CONF_NAME, "")).strip()
            if interval < MIN_SCAN_INTERVAL or interval > MAX_SCAN_INTERVAL:
                errors["base"] = "invalid_interval"
            else:
                updated_data = dict(self._config_entry.data)
                if name:
                    updated_data[CONF_NAME] = name
                elif CONF_NAME in updated_data:
                    updated_data.pop(CONF_NAME)
                title = name or f"{updated_data[CONF_HOST]} (unit {updated_data[CONF_UNIT_ID]})"
                if updated_data != self._config_entry.data or title != self._config_entry.title:
                    self.hass.config_entries.async_update_entry(
                        self._config_entry,
                        data=updated_data,
                        title=title,
                    )
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_SCAN_INTERVAL: interval,
                        CONF_VARIANT: variant,
                    },
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current_interval): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(CONF_VARIANT, default=current_variant): vol.In(VARIANT_LABELS),
                vol.Optional(CONF_NAME, default=current_name): vol.All(
                    str,
                    vol.Length(max=100),
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=data_schema, errors=errors)


def _build_unique_id(host: str, unit_id: int) -> str:
    """Create a unique identifier for a wallbox connection."""

    return f"{host.lower()}-{unit_id}"


class CannotConnect(HomeAssistantError):
    """Error raised when the Modbus bridge cannot connect."""


def _normalize_config_entry(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return a sanitized copy of user supplied configuration values."""

    return {
        CONF_HOST: str(data[CONF_HOST]).strip(),
        CONF_PORT: int(data[CONF_PORT]),
        CONF_UNIT_ID: int(data[CONF_UNIT_ID]),
        CONF_SCAN_INTERVAL: int(data[CONF_SCAN_INTERVAL]),
        CONF_VARIANT: data.get(CONF_VARIANT, DEFAULT_VARIANT),
        CONF_NAME: str(data.get(CONF_NAME, "")).strip(),
    }
