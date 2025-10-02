"""Number platform for Webasto Next Modbus integration."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RuntimeData
from .const import CONF_UNIT_ID, DOMAIN, NUMBER_REGISTERS
from .entity import WebastoRegisterEntity


async def async_setup_entry(
	hass: HomeAssistant,
	entry: ConfigEntry,
	async_add_entities: AddEntitiesCallback,
) -> None:
	"""Set up Webasto number entities."""

	runtime: RuntimeData = hass.data[DOMAIN][entry.entry_id]

	host = entry.data[CONF_HOST]
	unit_id = entry.data[CONF_UNIT_ID]

	entities = [
		WebastoNumber(runtime.coordinator, runtime.bridge, host, unit_id, register)
		for register in NUMBER_REGISTERS
	]

	async_add_entities(entities)


class WebastoNumber(WebastoRegisterEntity, NumberEntity):  # type: ignore[misc]
	"""Expose writable Modbus registers as number entities."""

	_attr_has_entity_name = True
	_attr_mode = NumberMode.BOX

	def __init__(self, coordinator, bridge, host: str, unit_id: int, register) -> None:
		super().__init__(coordinator, bridge, host, unit_id, register)

		if register.min_value is not None:
			self._attr_native_min_value = register.min_value
		if register.max_value is not None:
			self._attr_native_max_value = register.max_value
		if register.step is not None:
			self._attr_native_step = register.step
		if register.unit:
			self._attr_native_unit_of_measurement = register.unit

		self._write_only = register.write_only
		if self._write_only:
			self._attr_assumed_state = True

		if not self._write_only and coordinator.data:
			self._attr_native_value = coordinator.data.get(register.key)

	async def async_set_native_value(self, value: float) -> None:
		"""Write a value to the Modbus register."""

		int_value = int(round(value))

		if self._attr_native_min_value is not None:
			int_value = max(int_value, int(self._attr_native_min_value))
		if self._attr_native_max_value is not None:
			int_value = min(int_value, int(self._attr_native_max_value))

		await self._async_write_register(int_value)
		await self.coordinator.async_request_refresh()

	def _handle_coordinator_update(self) -> None:
		"""Update the native value from coordinator data."""

		if self._write_only:
			self._attr_native_value = None
		else:
			self._attr_native_value = self.get_coordinator_value()

		super()._handle_coordinator_update()
