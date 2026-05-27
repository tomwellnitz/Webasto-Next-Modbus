"""Binary sensor platform for the Webasto Next Modbus integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import WebastoConfigEntry
from .const import CONF_UNIT_ID, build_device_slug
from .coordinator import WebastoDataCoordinator
from .entity import build_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WebastoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the connectivity and charging binary sensors."""

    runtime = entry.runtime_data
    host = entry.data[CONF_HOST]
    unit_id = entry.data[CONF_UNIT_ID]
    async_add_entities(
        [
            WebastoConnectivitySensor(runtime.coordinator, host, unit_id, runtime.device_name),
            WebastoChargingSensor(runtime.coordinator, host, unit_id, runtime.device_name),
        ]
    )


class WebastoConnectivitySensor(  # type: ignore[misc]
    CoordinatorEntity[WebastoDataCoordinator], BinarySensorEntity
):
    """Reports whether the integration is currently reaching the wallbox."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "connected"

    def __init__(
        self,
        coordinator: WebastoDataCoordinator,
        host: str,
        unit_id: int,
        device_name: str,
    ) -> None:
        super().__init__(coordinator)
        prefix = build_device_slug(host, unit_id)
        self._unique_prefix = prefix
        self._device_name = device_name
        self._attr_unique_id = f"{prefix}-connected"
        self._attr_device_info = build_device_info(prefix, device_name, coordinator)

    @property
    def available(self) -> bool:
        # Deliberately always available: the point of this entity is to report
        # "on/off" even while the wallbox is unreachable. A plain
        # CoordinatorEntity would go "unavailable" instead, which is useless.
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success

    def _handle_coordinator_update(self) -> None:
        self._attr_device_info = build_device_info(
            self._unique_prefix, self._device_name, self.coordinator
        )
        super()._handle_coordinator_update()


class WebastoChargingSensor(  # type: ignore[misc]
    CoordinatorEntity[WebastoDataCoordinator], BinarySensorEntity
):
    """On while the wallbox is actively charging a vehicle."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING
    _attr_translation_key = "charging"

    def __init__(
        self,
        coordinator: WebastoDataCoordinator,
        host: str,
        unit_id: int,
        device_name: str,
    ) -> None:
        super().__init__(coordinator)
        prefix = build_device_slug(host, unit_id)
        self._unique_prefix = prefix
        self._device_name = device_name
        self._attr_unique_id = f"{prefix}-charging"
        self._attr_device_info = build_device_info(prefix, device_name, coordinator)

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return None
        value = data.get("charging_state")
        if value is None:
            return None
        try:
            return int(value) == 1
        except TypeError, ValueError:
            return None

    def _handle_coordinator_update(self) -> None:
        self._attr_device_info = build_device_info(
            self._unique_prefix, self._device_name, self.coordinator
        )
        super()._handle_coordinator_update()
