"""Sensor platform for Webasto Next Modbus integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import CONF_HOST, EntityCategory, UnitOfElectricPotential
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import WebastoConfigEntry
from .const import MODEL_NEXT, RegisterDefinition, get_sensor_registers
from .coordinator import WebastoDataCoordinator
from .entity import WebastoRegisterEntity, WebastoRestEntity
from .hub import ModbusBridge
from .rest_client import RestData
from .rest_coordinator import WebastoRestCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RestSensorDefinition:
    """Definition for a REST-based sensor."""

    key: str
    value_fn: Callable[[RestData], StateType | list[str] | None]
    device_class: str | None = None
    state_class: str | None = None
    unit: str | None = None
    entity_category: str | None = "diagnostic"
    translation_key: str | None = None
    entity_registry_enabled_default: bool = True


REST_SENSORS: list[RestSensorDefinition] = [
    RestSensorDefinition(
        key="comboard_firmware",
        value_fn=lambda d: d.comboard_sw_version,
        # Also shown on the device page (pushed to the device registry).
        entity_registry_enabled_default=False,
    ),
    RestSensorDefinition(
        key="powerboard_firmware",
        value_fn=lambda d: d.powerboard_sw_version,
        # Also shown on the device page (pushed to the device registry).
        entity_registry_enabled_default=False,
    ),
    RestSensorDefinition(
        key="plug_cycles",
        value_fn=lambda d: d.plug_cycles,
        state_class="total_increasing",
    ),
    RestSensorDefinition(
        key="error_count",
        value_fn=lambda d: d.error_counter,
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
        # None (not fetched yet) is unknown, an empty list means no errors.
        value_fn=lambda d: None if d.active_errors is None else ", ".join(d.active_errors) or "ok",
        entity_category=None,
        translation_key="active_errors",
    ),
]


PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WebastoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Webasto sensors from a config entry."""

    runtime = entry.runtime_data

    host = entry.data[CONF_HOST]

    entities: list[SensorEntity] = [
        WebastoSensor(
            runtime.coordinator,
            runtime.bridge,
            host,
            definition,
            runtime.device_name,
        )
        for definition in get_sensor_registers(runtime.model)
    ]

    # The diagnostic REST sensors only exist on the Next; the Unite's REST API
    # has no equivalent fields.
    if (rest := runtime.rest_coordinator) is not None and runtime.model == MODEL_NEXT:
        entities.extend(
            WebastoRestSensor(
                rest,
                host,
                definition,
                runtime.device_name,
                runtime.coordinator.device_model_name,
            )
            for definition in REST_SENSORS
        )

    async_add_entities(entities)


class WebastoSensor(WebastoRegisterEntity, SensorEntity):
    """Representation of a Webasto Modbus register as a sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WebastoDataCoordinator,
        bridge: ModbusBridge,
        host: str,
        register: RegisterDefinition,
        device_name: str,
    ) -> None:
        super().__init__(coordinator, bridge, host, register, device_name)

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

        if register.suggested_display_precision is not None:
            self._attr_suggested_display_precision = register.suggested_display_precision

        self._options_map = register.options
        self._unknown_options_logged: set[str] = set()
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
            except ValueError, TypeError:
                # Fallback to raw value if formatting fails
                pass

        if self._options_map:
            self._attr_native_value = self._map_option(value)
        else:
            self._attr_native_value = value

    def _map_option(self, value: Any) -> str | None:
        """Map a raw enum code to its option, or ``None`` if it is undocumented.

        An enum sensor's state must be one of its options; Home Assistant
        rejects anything else, so an unknown code (e.g. a new fault code from a
        firmware update) is reported as unknown instead of breaking the entity.
        """
        assert self._options_map is not None
        try:
            option = self._options_map.get(int(value))
        except ValueError, TypeError:
            option = None
        if option is None:
            raw = str(value)
            if raw not in self._unknown_options_logged:
                self._unknown_options_logged.add(raw)
                _LOGGER.debug("Undocumented value %s for %s", raw, self._register.key)
        return option


class WebastoRestSensor(WebastoRestEntity, SensorEntity):
    """Sensor entity for REST API data."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WebastoRestCoordinator,
        host: str,
        definition: RestSensorDefinition,
        device_name: str,
        model_name: str,
    ) -> None:
        super().__init__(coordinator, host, definition.key, device_name, model_name)
        self._definition = definition

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
        if definition.translation_key:
            self._attr_translation_key = definition.translation_key
        self._attr_entity_registry_enabled_default = definition.entity_registry_enabled_default

        self._update_value()

    def _handle_coordinator_update(self) -> None:
        """Update state from coordinator data."""
        self._update_value()
        super()._handle_coordinator_update()

    def _update_value(self) -> None:
        """Update the native value from REST data."""
        rest_data = self.rest_data
        if rest_data is None:
            self._attr_native_value = None
            return

        value = self._definition.value_fn(rest_data)

        if isinstance(value, list):
            value = ", ".join(str(v) for v in value) or "ok"
        self._attr_native_value = value
