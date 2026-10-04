"""Config and options flow for the Webasto Next Modbus integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from modbus_connection import ModbusTcpParams

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
from .rest_client import AuthenticationError, RestClient, RestClientError

_LOGGER = logging.getLogger(__name__)


class WebastoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Webasto Next Modbus config flow."""

    VERSION = 1
    MINOR_VERSION = 3

    async def async_step_user(
        self, user_input: Mapping[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial configuration step."""

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

        The new settings are tested before they are saved. Probing the same
        wallbox the entry already talks to shares the entry's connection, so
        the single Modbus TCP slot is not an obstacle.
        """

        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = int(user_input[CONF_PORT])
            unit_id = int(user_input[CONF_UNIT_ID])
            name = str(user_input.get(CONF_NAME, "")).strip()

            new_unique_id = _build_unique_id(host, unit_id)
            for other in self._async_current_entries():
                if other.entry_id != entry.entry_id and other.unique_id == new_unique_id:
                    return self.async_abort(reason="already_configured")

            try:
                await self._async_validate_and_connect(
                    {
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_UNIT_ID: unit_id,
                        # The options flow can change the model; setup uses
                        # that one, so test against the same register map.
                        CONF_MODEL: entry.options.get(
                            CONF_MODEL, entry.data.get(CONF_MODEL, DEFAULT_MODEL)
                        ),
                    }
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
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

                # Update the entry and let the existing update listener perform
                # the single reload. We deliberately do not use a reloading
                # config-flow helper here: combining it with the update listener
                # is deprecated (HA 2026.6, error from 2026.12) because it
                # reloads twice.
                self.hass.config_entries.async_update_entry(
                    entry,
                    data=new_data,
                    title=title,
                    unique_id=new_unique_id,
                )
                return self.async_abort(reason="reconfigure_successful")

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

        if user_input is not None:
            # Keep what the user typed when the test failed.
            data_schema = self.add_suggested_values_to_schema(data_schema, user_input)
        return self.async_show_form(step_id="reconfigure", data_schema=data_schema, errors=errors)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Handle re-authentication when the REST API rejects the credentials."""

        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: Mapping[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask the user for new REST API credentials and validate them."""

        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        current_username = entry.options.get(
            CONF_REST_USERNAME, entry.data.get(CONF_REST_USERNAME, DEFAULT_REST_USERNAME)
        )

        if user_input is not None:
            username = str(user_input.get(CONF_REST_USERNAME, current_username)).strip()
            password = str(user_input.get(CONF_REST_PASSWORD, ""))
            try:
                await _async_validate_rest(
                    self.hass,
                    entry.data[CONF_HOST],
                    username,
                    password,
                    entry.options.get(CONF_MODEL, entry.data.get(CONF_MODEL, DEFAULT_MODEL)),
                )
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except RestClientError as err:
                _LOGGER.warning("REST API validation failed during reauth: %s", err)
                errors["base"] = "rest_cannot_connect"
            else:
                new_options = dict(entry.options)
                new_options[CONF_REST_ENABLED] = True
                new_options[CONF_REST_USERNAME] = username
                new_options[CONF_REST_PASSWORD] = password
                # The update listener performs the single reload (see the note
                # in async_step_reconfigure).
                self.hass.config_entries.async_update_entry(entry, options=new_options)
                return self.async_abort(reason="reauth_successful")

        data_schema = vol.Schema(
            {
                vol.Required(CONF_REST_USERNAME, default=current_username): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Required(CONF_REST_PASSWORD): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            }
        )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"host": entry.data.get(CONF_HOST, "")},
        )

    async def _async_validate_and_connect(self, data: Mapping[str, Any]) -> None:
        """Validate user input with a single Modbus test read.

        The temporary unit shares the connection of an entry that already
        talks to this wallbox (its only Modbus TCP slot), and opens and closes
        its own one otherwise.
        """
        host = data[CONF_HOST]
        port = int(data[CONF_PORT])
        unit_id = int(data[CONF_UNIT_ID])
        params = ModbusTcpParams(host=host, port=port)

        try:
            async with async_get_temporary_unit(self.hass, params, unit_id) as unit:
                bridge = ModbusBridge(
                    unit,
                    host=host,
                    port=port,
                    unit_id=unit_id,
                    registers=get_readable_registers(data.get(CONF_MODEL, DEFAULT_MODEL)),
                )
                await bridge.async_test_connection()
        except (WebastoModbusError, HomeAssistantError) as err:
            raise CannotConnect from err

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

            # Validate the REST connection if enabled.
            if not errors and rest_enabled and rest_password:
                try:
                    await _async_validate_rest(
                        self.hass,
                        config_entry.data[CONF_HOST],
                        rest_username,
                        rest_password,
                        model,
                    )
                except AuthenticationError:
                    errors["base"] = "invalid_auth"
                except RestClientError as err:
                    _LOGGER.warning("REST API validation failed: %s", err)
                    errors["base"] = "rest_cannot_connect"

            if not errors:
                updated_data = dict(config_entry.data)
                if name:
                    updated_data[CONF_NAME] = name
                elif CONF_NAME in updated_data:
                    updated_data.pop(CONF_NAME)
                title = name or f"{updated_data[CONF_HOST]} (unit {updated_data[CONF_UNIT_ID]})"

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

                # Apply data, title and options in one update so the update
                # listener reloads the entry once. Finishing the flow with the
                # same options afterwards is then a no-op.
                self.hass.config_entries.async_update_entry(
                    config_entry,
                    data=updated_data,
                    title=title,
                    options=options_data,
                )
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


async def _async_validate_rest(
    hass: HomeAssistant, host: str, username: str, password: str, model: str
) -> None:
    """Confirm REST credentials by logging in to the wallbox web interface.

    Raises ``AuthenticationError`` for rejected credentials and another
    ``RestClientError`` if the wallbox can't be reached. Uses Home Assistant's
    shared aiohttp session; ``disconnect()`` only clears the token.
    """

    session = async_get_clientsession(hass, verify_ssl=False)
    client = RestClient(host, username, password, session, model=model)
    try:
        await client.connect()
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
