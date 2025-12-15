"""Sensor platform for Webasto Next Modbus integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, EntityCategory, UnitOfElectricPotential
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RuntimeData
from .const import CONF_UNIT_ID, DOMAIN, SENSOR_REGISTERS
from .coordinator import WebastoDataCoordinator
from .entity import WebastoRegisterEntity, WebastoRestEntity
from .rest_client import RestData


@dataclass(frozen=True)
class RestSensorDefinition:
    """Definition for a REST-based sensor."""

    key: str
    value_fn: Callable[[RestData], str | int | float | list[str] | None]
    icon: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    unit: str | None = None
    entity_category: str | None = "diagnostic"


REST_SENSORS: list[RestSensorDefinition] = [
    RestSensorDefinition(
        key="comboard_firmware",
        value_fn=lambda d: d.comboard_sw_version,
        icon="mdi:chip",
    ),
    RestSensorDefinition(
        key="powerboard_firmware",
        value_fn=lambda d: d.powerboard_sw_version,
        icon="mdi:chip",
    ),
    RestSensorDefinition(
        key="mac_address_ethernet",
        value_fn=lambda d: d.mac_address_ethernet,
        icon="mdi:ethernet",
    ),
    RestSensorDefinition(
        key="mac_address_wifi",
        value_fn=lambda d: d.mac_address_wifi,
        icon="mdi:wifi",
    ),
    RestSensorDefinition(
        key="plug_cycles",
        value_fn=lambda d: d.plug_cycles,
        icon="mdi:ev-plug-type2",
        state_class="total_increasing",
    ),
    RestSensorDefinition(
        key="error_count",
        value_fn=lambda d: d.error_counter,
        icon="mdi:alert-circle",
        state_class="total_increasing",
    ),
    RestSensorDefinition(
        key="signal_voltage_l1",
        value_fn=lambda d: d.signal_voltage_l1,
        device_class="voltage",
        state_class="measurement",
        unit=UnitOfElectricPotential.VOLT,
        entity_category=None,
    ),
    RestSensorDefinition(
        key="signal_voltage_l2",
        value_fn=lambda d: d.signal_voltage_l2,
        device_class="voltage",
        state_class="measurement",
        unit=UnitOfElectricPotential.VOLT,
        entity_category=None,
    ),
    RestSensorDefinition(
        key="signal_voltage_l3",
        value_fn=lambda d: d.signal_voltage_l3,
        device_class="voltage",
        state_class="measurement",
        unit=UnitOfElectricPotential.VOLT,
        entity_category=None,
    ),
    RestSensorDefinition(
        key="active_errors",
        value_fn=lambda d: ", ".join(d.active_errors) if d.active_errors else "None",
        icon="mdi:alert",
        entity_category=None,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Webasto sensors from a config entry."""

    runtime: RuntimeData = hass.data[DOMAIN][entry.entry_id]

    host = entry.data[CONF_HOST]
    unit_id = entry.data[CONF_UNIT_ID]

    entities: list[SensorEntity] = [
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

    # Add REST sensors if REST API is enabled
    if runtime.coordinator.rest_enabled:
        entities.extend(
            WebastoRestSensor(
                runtime.coordinator,
                host,
                unit_id,
                definition,
                runtime.device_name,
            )
            for definition in REST_SENSORS
        )

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


class WebastoRestSensor(WebastoRestEntity, SensorEntity):  # type: ignore[misc]
    """Sensor entity for REST API data."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WebastoDataCoordinator,
        host: str,
        unit_id: int,
        definition: RestSensorDefinition,
        device_name: str,
    ) -> None:
        super().__init__(coordinator, host, unit_id, definition.key, device_name)
        self._definition = definition

        if definition.icon:
            self._attr_icon = definition.icon
        if definition.device_class:
            try:
                self._attr_device_class = SensorDeviceClass(definition.device_class)
            except ValueError:
                pass
        if definition.state_class:
            try:
                self._attr_state_class = SensorStateClass(definition.state_class)
            except ValueError:
                pass
        if definition.unit:
            self._attr_native_unit_of_measurement = definition.unit
        if definition.entity_category:
            try:
                self._attr_entity_category = EntityCategory(definition.entity_category)
            except ValueError:
                pass

    @property
    def native_value(self) -> str | int | float | None:
        """Return the sensor value from REST data."""
        rest_data = self.coordinator.rest_data
        if rest_data is None:
            return None
        value = self._definition.value_fn(rest_data)
        # Handle list values (like active_errors)
        if isinstance(value, list):
            return ", ".join(str(v) for v in value) if value else "None"
        return value
