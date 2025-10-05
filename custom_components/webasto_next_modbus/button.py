"""Button platform for Webasto Next Modbus integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RuntimeData
from .const import (
	BUTTON_REGISTERS,
	CONF_UNIT_ID,
	DOMAIN,
	KEEPALIVE_TRIGGER_VALUE,
	SESSION_COMMAND_START_VALUE,
	SESSION_COMMAND_STOP_VALUE,
)
from .device_trigger import TRIGGER_KEEPALIVE_SENT, async_fire_device_trigger
from .entity import WebastoRegisterEntity


async def async_setup_entry(
	hass: HomeAssistant,
	entry: ConfigEntry,
	async_add_entities: AddEntitiesCallback,
) -> None:
	"""Set up Webasto button entities."""

	runtime: RuntimeData = hass.data[DOMAIN][entry.entry_id]

	host = entry.data[CONF_HOST]
	unit_id = entry.data[CONF_UNIT_ID]

	entities = [
		WebastoButton(
			runtime.coordinator,
			runtime.bridge,
			host,
			unit_id,
			register,
			runtime.device_name,
		)
		for register in BUTTON_REGISTERS
	]

	async_add_entities(entities)


class WebastoButton(WebastoRegisterEntity, ButtonEntity):  # type: ignore[misc]
	"""Represent write-only Modbus actions as buttons."""

	_attr_has_entity_name = True

	async def async_press(self) -> None:
		"""Trigger the Modbus action associated with the register."""

		if self.register.key == "send_keepalive":
			value = KEEPALIVE_TRIGGER_VALUE
		elif self.register.key == "start_session":
			value = SESSION_COMMAND_START_VALUE
		elif self.register.key == "stop_session":
			value = SESSION_COMMAND_STOP_VALUE
		else:
			value = 1
		await self._async_write_register(value)
		if self.register.key == "send_keepalive":
			async_fire_device_trigger(
				self.coordinator.hass,
				self._unique_prefix,
				TRIGGER_KEEPALIVE_SENT,
				{"source": "button"},
			)
		await self.coordinator.async_request_refresh()
