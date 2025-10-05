"""Number platform for Webasto Next Modbus integration."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.exceptions import HomeAssistantError

from . import RuntimeData
from .const import CONF_UNIT_ID, DOMAIN, NUMBER_REGISTERS, SIGNAL_REGISTER_WRITTEN
from .entity import WebastoRegisterEntity


_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
	hass: HomeAssistant,
	entry: ConfigEntry,
	async_add_entities: AddEntitiesCallback,
) -> None:
	"""Set up Webasto number entities."""

	runtime: RuntimeData = hass.data[DOMAIN][entry.entry_id]

	host = entry.data[CONF_HOST]
	unit_id = entry.data[CONF_UNIT_ID]

	max_current = runtime.max_current
	entities = [
		WebastoNumber(
			runtime.coordinator,
			runtime.bridge,
			host,
			unit_id,
			register,
			runtime.device_name,
			max_current,
		)
		for register in NUMBER_REGISTERS
	]

	async_add_entities(entities)


class WebastoNumber(WebastoRegisterEntity, RestoreNumber, NumberEntity):  # type: ignore[misc]
	"""Expose writable Modbus registers as number entities."""

	_attr_has_entity_name = True
	_attr_mode = NumberMode.BOX

	def __init__(
		self,
		coordinator,
		bridge,
		host: str,
		unit_id: int,
		register,
		device_name: str,
		variant_max_current: int | None = None,
	) -> None:
		super().__init__(coordinator, bridge, host, unit_id, register, device_name)

		if register.min_value is not None:
			self._attr_native_min_value = register.min_value
		if register.max_value is not None:
			self._attr_native_max_value = register.max_value
		if register.step is not None:
			self._attr_native_step = register.step
		if register.unit:
			self._attr_native_unit_of_measurement = register.unit

		self._last_written_value: int | None = None
		self._write_only = register.write_only
		if self._write_only:
			self._attr_assumed_state = True

		if coordinator.data:
			initial = coordinator.data.get(register.key)
			if not self._write_only:
				self._attr_native_value = initial
			elif initial is not None:
				try:
					self._last_written_value = int(initial)
				except (TypeError, ValueError):
					self._last_written_value = None

		self._variant_max_current = variant_max_current
		if (
			register.key in {"failsafe_current_a", "set_current_a"}
			and variant_max_current is not None
		):
			current_max = self._attr_native_max_value
			if current_max is None:
				current_max = float(variant_max_current)
			self._attr_native_max_value = float(min(current_max, variant_max_current))

	async def async_set_native_value(self, value: float) -> None:
		"""Write a value to the Modbus register."""

		int_value = int(round(value))

		if self._attr_native_min_value is not None:
			int_value = max(int_value, int(self._attr_native_min_value))
		if self._attr_native_max_value is not None:
			int_value = min(int_value, int(self._attr_native_max_value))

		await self._async_write_register(int_value)
		self._last_written_value = int_value
		self._attr_native_value = int_value
		if self.hass is not None:
			self.async_write_ha_state()
		await self.coordinator.async_request_refresh()

	def _handle_coordinator_update(self) -> None:
		"""Update the native value from coordinator data."""

		if self._write_only:
			if self._last_written_value is not None:
				self._attr_native_value = self._last_written_value
			else:
				self._attr_native_value = None
		else:
			value = self.get_coordinator_value()
			self._attr_native_value = value

		super()._handle_coordinator_update()

	async def async_added_to_hass(self) -> None:
		"""Subscribe to dispatcher events once entity is added to Home Assistant."""

		await super().async_added_to_hass()
		if self._write_only:
			last_number_data = await self.async_get_last_number_data()
			if last_number_data and last_number_data.native_value is not None:
				try:
					restored_value = float(last_number_data.native_value)
				except (TypeError, ValueError):
					_LOGGER.debug(
						"Ignoring invalid restored charging current %s for %s",
						last_number_data.native_value,
						self.entity_id,
					)
				else:
					try:
						await self.async_set_native_value(restored_value)
					except HomeAssistantError as err:
						_LOGGER.warning(
							"Failed to re-apply charging current %s for %s: %s",
							restored_value,
							self.entity_id,
							err,
						)
		if self.hass is None:
			return
		remove = async_dispatcher_connect(
			self.hass,
			SIGNAL_REGISTER_WRITTEN,
			self._handle_register_written,
		)
		self.async_on_remove(remove)

	def _handle_register_written(
		self,
		device_slug: str,
		register_key: str,
		value: int | float | None,
	) -> None:
		"""Update entity state when a service writes to the backing register."""

		if device_slug != self._unique_prefix or register_key != self.register.key:
			return
		if value is None:
			int_value: int | None = None
		else:
			try:
				int_value = int(value)
			except (TypeError, ValueError):
				return
		self._last_written_value = int_value
		self._attr_native_value = int_value
		if self.hass is not None:
			self.async_write_ha_state()
