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
    """Set up the connectivity binary sensor."""

    runtime = entry.runtime_data
    async_add_entities(
        [
            WebastoConnectivitySensor(
                runtime.coordinator,
                entry.data[CONF_HOST],
                entry.data[CONF_UNIT_ID],
                runtime.device_name,
            )
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
