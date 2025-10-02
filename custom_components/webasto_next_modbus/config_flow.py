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

from .const import (
	CONF_SCAN_INTERVAL,
	CONF_UNIT_ID,
	DEFAULT_PORT,
	DEFAULT_SCAN_INTERVAL,
	DEFAULT_UNIT_ID,
	DOMAIN,
	MAX_SCAN_INTERVAL,
	MIN_SCAN_INTERVAL,
)
from .hub import ModbusBridge, WebastoModbusError

_LOGGER = logging.getLogger(__name__)


class WebastoConfigFlow(config_entries.ConfigFlow):
	"""Handle a Webasto Next Modbus config flow."""

	VERSION = 1
	domain = DOMAIN

	_host: str | None = None
	_unit_id: int | None = None

	async def async_step_user(
		self, user_input: Mapping[str, Any] | None = None
	) -> config_entries.ConfigFlowResult:
		"""Handle the initial configuration step."""

		errors: dict[str, str] = {}

		if user_input is not None:
			try:
				await self._async_validate_and_connect(user_input)
			except CannotConnect:
				errors["base"] = "cannot_connect"
			except TimeoutError:
				errors["base"] = "cannot_connect"
			except Exception as err:  # pragma: no cover - defensive
				errors["base"] = "unknown"
				_LOGGER.exception("Unexpected error validating config: %s", err)
			else:
				await self.async_set_unique_id(
					_build_unique_id(user_input[CONF_HOST], user_input[CONF_UNIT_ID])
				)
				self._abort_if_unique_id_configured()

				data = {
					CONF_HOST: user_input[CONF_HOST],
					CONF_PORT: user_input[CONF_PORT],
					CONF_UNIT_ID: user_input[CONF_UNIT_ID],
					CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
				}

				title = f"{user_input[CONF_HOST]} (unit {user_input[CONF_UNIT_ID]})"

				return self.async_create_entry(
					title=title,
					data=data,
					options={CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL]},
				)

		defaults = user_input or {}

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
				): vol.All(
					vol.Coerce(int),
					vol.Range(min=1, max=255),
				),
				vol.Required(
					CONF_SCAN_INTERVAL,
					default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
				): vol.All(
					vol.Coerce(int),
					vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
				),
			}
		)

		return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)

	async def _async_validate_and_connect(self, data: Mapping[str, Any]) -> None:
		"""Validate user input by performing a Modbus test read."""

		bridge = ModbusBridge(
			host=data[CONF_HOST],
			port=data[CONF_PORT],
			unit_id=data[CONF_UNIT_ID],
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

		errors: dict[str, str] = {}
		current_interval = self._config_entry.options.get(
			CONF_SCAN_INTERVAL,
			self._config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
		)

		if user_input is not None:
			interval = user_input[CONF_SCAN_INTERVAL]
			if interval < MIN_SCAN_INTERVAL or interval > MAX_SCAN_INTERVAL:
				errors["base"] = "invalid_interval"
			else:
				return self.async_create_entry(title="", data={CONF_SCAN_INTERVAL: interval})

		data_schema = vol.Schema(
			{
				vol.Required(CONF_SCAN_INTERVAL, default=current_interval): vol.All(
					vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
				)
			}
		)

		return self.async_show_form(step_id="init", data_schema=data_schema, errors=errors)


def _build_unique_id(host: str, unit_id: int) -> str:
	"""Create a unique identifier for a wallbox connection."""

	return f"{host.lower()}-{unit_id}"


class CannotConnect(HomeAssistantError):
	"""Error raised when the Modbus bridge cannot connect."""

