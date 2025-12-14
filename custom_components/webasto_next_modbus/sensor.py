"""Sensor platform for Webasto Next Modbus integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RuntimeData
from .const import CONF_UNIT_ID, DOMAIN, SENSOR_REGISTERS
from .entity import WebastoRegisterEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Webasto sensors from a config entry."""

    runtime: RuntimeData = hass.data[DOMAIN][entry.entry_id]

    host = entry.data[CONF_HOST]
    unit_id = entry.data[CONF_UNIT_ID]

    entities = [
        WebastoSensor(
            runtime.coordinator,
            runtime.bridge,
            host,
            unit_id,
            definition,
            runtime.device_name,
        )
        for definition in SENSOR_REGISTERS
    ]

    async_add_entities(entities)


class WebastoSensor(WebastoRegisterEntity, SensorEntity):  # type: ignore[misc]
    """Representation of a Webasto Modbus register as a sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        bridge,
        host: str,
        unit_id: int,
        register,
        device_name: str,
    ) -> None:
        super().__init__(coordinator, bridge, host, unit_id, register, device_name)

        if register.device_class:
            try:
                self._attr_device_class = SensorDeviceClass(register.device_class)
            except ValueError:
                pass
        if register.state_class:
            try:
                self._attr_state_class = SensorStateClass(register.state_class)
            except ValueError:
                pass
        if register.unit:
            self._attr_native_unit_of_measurement = register.unit

        self._options_map = register.options
        if register.options:
            self._attr_options = list(register.options.values())
        if register.translation_key:
            self._attr_translation_key = register.translation_key

        self._update_value()

    def _handle_coordinator_update(self) -> None:
        """Update state from coordinator data."""
        self._update_value()
        super()._handle_coordinator_update()

    def _update_value(self) -> None:
        """Update the native value from the coordinator."""
        value = self.get_coordinator_value()

        if value is None:
            self._attr_native_value = None
            return

        # Handle time formatting for start/end time (hhmmss -> HH:MM:SS)
        if self._register.key in ("session_start_time", "session_end_time"):
            try:
                val_int = int(value)
                # Pad with zeros to ensure 6 digits (e.g., 93000 -> 093000)
                val_str = f"{val_int:06d}"
                self._attr_native_value = f"{val_str[:2]}:{val_str[2:4]}:{val_str[4:]}"
                return
            except (ValueError, TypeError):
                # Fallback to raw value if formatting fails
                pass

        if self._options_map:
            try:
                self._attr_native_value = self._options_map.get(int(value), str(value))
            except (ValueError, TypeError):
                self._attr_native_value = value
        else:
            self._attr_native_value = value
