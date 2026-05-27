"""Config and options flow for the Webasto Next Modbus integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .const import (
    CONF_MODEL,
    CONF_NAME,
    CONF_REST_ENABLED,
    CONF_REST_PASSWORD,
    CONF_REST_USERNAME,
    CONF_SCAN_INTERVAL,
    CONF_UNIT_ID,
    CONF_VARIANT,
    DEFAULT_MODEL,
    DEFAULT_PORT,
    DEFAULT_REST_USERNAME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DEFAULT_VARIANT,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    MODEL_LABELS,
    VARIANT_LABELS,
    get_readable_registers,
)
from .hub import ModbusBridge, WebastoModbusError

_LOGGER = logging.getLogger(__name__)


class WebastoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Webasto Next Modbus config flow."""

    VERSION = 1

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
                self._abort_if_unique_id_configured(reload_on_update=False)

                name = normalized_input.get(CONF_NAME, "")

                data = {
                    CONF_HOST: normalized_input[CONF_HOST],
                    CONF_PORT: normalized_input[CONF_PORT],
                    CONF_UNIT_ID: normalized_input[CONF_UNIT_ID],
                    CONF_SCAN_INTERVAL: normalized_input[CONF_SCAN_INTERVAL],
                    CONF_VARIANT: normalized_input[CONF_VARIANT],
                    CONF_MODEL: normalized_input[CONF_MODEL],
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
                        CONF_MODEL: normalized_input[CONF_MODEL],
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
                    CONF_MODEL,
                    default=defaults.get(CONF_MODEL, DEFAULT_MODEL),
                ): vol.In(MODEL_LABELS),
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

    async def async_step_reconfigure(
        self, user_input: Mapping[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Let the user change the connection settings of an existing entry.

        The new settings are validated by the reload that follows: Home
        Assistant unloads the entry first (which closes the existing Modbus
        connection via ``async_unload_entry``), then sets it up again against
        the new host/port/unit and validates on the first refresh. We do not
        open a second connection to test here on purpose -- the wallbox accepts
        only one Modbus TCP connection at a time and the old one is still held
        by the running entry, so a probe would be refused or test stale data.
        """

        entry = self._get_reconfigure_entry()

        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = int(user_input[CONF_PORT])
            unit_id = int(user_input[CONF_UNIT_ID])
            name = str(user_input.get(CONF_NAME, "")).strip()

            new_unique_id = _build_unique_id(host, unit_id)
            for other in self._async_current_entries():
                if other.entry_id != entry.entry_id and other.unique_id == new_unique_id:
                    return self.async_abort(reason="already_configured")

            new_data = dict(entry.data)
            new_data[CONF_HOST] = host
            new_data[CONF_PORT] = port
            new_data[CONF_UNIT_ID] = unit_id
            if name:
                new_data[CONF_NAME] = name
                title = name
            else:
                new_data.pop(CONF_NAME, None)
                title = f"{host} (unit {unit_id})"

            return self.async_update_reload_and_abort(
                entry,
                data=new_data,
                title=title,
                unique_id=new_unique_id,
            )

        current = entry.data
        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=current.get(CONF_HOST, "")): vol.All(
                    str,
                    vol.Length(min=1),
                ),
                vol.Required(
                    CONF_PORT,
                    default=current.get(CONF_PORT, DEFAULT_PORT),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=1, max=65535),
                ),
                vol.Required(
                    CONF_UNIT_ID,
                    default=current.get(CONF_UNIT_ID, DEFAULT_UNIT_ID),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=255,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(CONF_NAME, default=current.get(CONF_NAME, "")): vol.All(
                    str,
                    vol.Length(max=100),
                ),
            }
        )

        return self.async_show_form(step_id="reconfigure", data_schema=data_schema)

    async def _async_validate_and_connect(self, data: Mapping[str, Any]) -> None:
        """Validate user input by performing a Modbus test read."""
        host = data[CONF_HOST]
        port = int(data[CONF_PORT])
        unit_id = int(data[CONF_UNIT_ID])

        # Check if there's already a running entry for this host - reuse its bridge
        existing_bridge = self._get_existing_bridge(host, unit_id)
        if existing_bridge is not None:
            try:
                await existing_bridge.async_test_connection()
                return
            except WebastoModbusError as err:
                raise CannotConnect from err

        # No existing bridge, create a temporary one for validation
        bridge = ModbusBridge(
            host=host,
            port=port,
            unit_id=unit_id,
            registers=get_readable_registers(data.get(CONF_MODEL, DEFAULT_MODEL)),
        )

        try:
            await bridge.async_connect()
            await bridge.async_test_connection()
        except WebastoModbusError as err:
            raise CannotConnect from err
        finally:
            await bridge.async_close()

    def _get_existing_bridge(self, host: str, unit_id: int) -> ModbusBridge | None:
        """Return the bridge for an existing entry if available."""
        from . import RuntimeData

        for entry in self.hass.config_entries.async_loaded_entries(DOMAIN):
            runtime = getattr(entry, "runtime_data", None)
            if not isinstance(runtime, RuntimeData):
                continue
            bridge = runtime.bridge
            # Check if this bridge matches the host/unit_id we're testing
            if bridge.host == host and bridge.unit_id == unit_id:
                return bridge
        return None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler."""

        return WebastoOptionsFlow()


class WebastoOptionsFlow(config_entries.OptionsFlow):
    """Handle Webasto Next options flow.

    Home Assistant injects ``self.config_entry`` on the instance after
    construction (since 2024.12); we deliberately do not store our own
    reference, which avoids the deprecation warning about explicit
    options-flow ``config_entry`` assignment.
    """

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

        config_entry = self.config_entry

        errors: dict[str, str] = {}
        current_interval = config_entry.options.get(
            CONF_SCAN_INTERVAL,
            config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        current_variant = config_entry.options.get(
            CONF_VARIANT,
            config_entry.data.get(CONF_VARIANT, DEFAULT_VARIANT),
        )
        current_model = config_entry.options.get(
            CONF_MODEL,
            config_entry.data.get(CONF_MODEL, DEFAULT_MODEL),
        )
        current_name = config_entry.data.get(CONF_NAME, "")
        current_rest_enabled = config_entry.options.get(
            CONF_REST_ENABLED,
            config_entry.data.get(CONF_REST_ENABLED, False),
        )
        current_rest_username = config_entry.options.get(
            CONF_REST_USERNAME,
            config_entry.data.get(CONF_REST_USERNAME, DEFAULT_REST_USERNAME),
        )

        if user_input is not None:
            interval = int(user_input[CONF_SCAN_INTERVAL])
            variant = user_input[CONF_VARIANT]
            model = user_input.get(CONF_MODEL, current_model)
            name = str(user_input.get(CONF_NAME, "")).strip()
            rest_enabled = user_input.get(CONF_REST_ENABLED, False)
            rest_username = str(user_input.get(CONF_REST_USERNAME, DEFAULT_REST_USERNAME)).strip()
            rest_password = user_input.get(CONF_REST_PASSWORD, "")

            if interval < MIN_SCAN_INTERVAL or interval > MAX_SCAN_INTERVAL:
                errors["base"] = "invalid_interval"
            elif rest_enabled and not rest_password:
                # Check if password was previously set (we don't show it)
                existing_password = config_entry.options.get(
                    CONF_REST_PASSWORD,
                    config_entry.data.get(CONF_REST_PASSWORD, ""),
                )
                if not existing_password:
                    errors["base"] = "rest_password_required"
                else:
                    rest_password = existing_password

            if not errors:
                # Validate REST connection if enabled
                if rest_enabled and rest_password:
                    try:
                        await self._validate_rest_connection(
                            config_entry.data[CONF_HOST],
                            rest_username,
                            rest_password,
                        )
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.warning("REST API validation failed: %s", err)
                        errors["base"] = "rest_cannot_connect"

            if not errors:
                updated_data = dict(config_entry.data)
                if name:
                    updated_data[CONF_NAME] = name
                elif CONF_NAME in updated_data:
                    updated_data.pop(CONF_NAME)
                title = name or f"{updated_data[CONF_HOST]} (unit {updated_data[CONF_UNIT_ID]})"
                if updated_data != config_entry.data or title != config_entry.title:
                    self.hass.config_entries.async_update_entry(
                        config_entry,
                        data=updated_data,
                        title=title,
                    )

                options_data: dict[str, Any] = {
                    CONF_SCAN_INTERVAL: interval,
                    CONF_VARIANT: variant,
                    CONF_MODEL: model,
                    CONF_REST_ENABLED: rest_enabled,
                }
                if rest_enabled:
                    options_data[CONF_REST_USERNAME] = rest_username
                    if rest_password:
                        options_data[CONF_REST_PASSWORD] = rest_password

                return self.async_create_entry(title="", data=options_data)

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
                vol.Required(CONF_MODEL, default=current_model): vol.In(MODEL_LABELS),
                vol.Required(CONF_VARIANT, default=current_variant): vol.In(VARIANT_LABELS),
                vol.Optional(CONF_NAME, default=current_name): vol.All(
                    str,
                    vol.Length(max=100),
                ),
                vol.Optional(CONF_REST_ENABLED, default=current_rest_enabled): bool,
                vol.Optional(
                    CONF_REST_USERNAME, default=current_rest_username
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Optional(CONF_REST_PASSWORD): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=data_schema, errors=errors)

    async def _validate_rest_connection(self, host: str, username: str, password: str) -> None:
        """Validate REST API connection."""
        from .rest_client import RestClient, RestClientError

        client = RestClient(host, username, password)
        try:
            if not await client.test_connection():
                msg = "REST API connection test failed"
                raise RestClientError(msg)
        finally:
            await client.disconnect()


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
        CONF_MODEL: data.get(CONF_MODEL, DEFAULT_MODEL),
        CONF_VARIANT: data.get(CONF_VARIANT, DEFAULT_VARIANT),
        CONF_NAME: str(data.get(CONF_NAME, "")).strip(),
    }
