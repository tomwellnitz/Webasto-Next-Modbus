"""Switch platform for Webasto Next Modbus integration."""

from __future__ import annotations

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RuntimeData
from .const import CONF_UNIT_ID, DOMAIN
from .coordinator import WebastoDataCoordinator
from .entity import WebastoRestEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Webasto switch entities."""
    runtime: RuntimeData = hass.data[DOMAIN][entry.entry_id]

    host = entry.data[CONF_HOST]
    unit_id = entry.data[CONF_UNIT_ID]

    entities: list[SwitchEntity] = []

    # Add Free Charging switch if REST API is enabled
    if runtime.coordinator.rest_enabled:
        entities.append(
            WebastoFreeChargingSwitch(
                runtime.coordinator,
                host,
                unit_id,
                runtime.device_name,
            )
        )

    async_add_entities(entities)


class WebastoFreeChargingSwitch(WebastoRestEntity, SwitchEntity):  # type: ignore[misc]
    """Switch entity for Free Charging mode via REST API."""

    _attr_has_entity_name = True
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:car-electric"

    def __init__(
        self,
        coordinator: WebastoDataCoordinator,
        host: str,
        unit_id: int,
        device_name: str,
    ) -> None:
        """Initialize the Free Charging switch."""
        super().__init__(
            coordinator, host, unit_id, "free_charging", device_name, coordinator._rest_client
        )
        self._pending_state: bool | None = None
        self._attr_is_on: bool | None = None

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self._pending_state is not None:
            self._attr_is_on = self._pending_state
        else:
            rest_data = self.coordinator.rest_data
            self._attr_is_on = None if rest_data is None else rest_data.free_charging_enabled
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: object) -> None:
        """Enable free charging."""
        await self._set_free_charging(enabled=True)

    async def async_turn_off(self, **kwargs: object) -> None:
        """Disable free charging."""
        await self._set_free_charging(enabled=False)

    async def _set_free_charging(self, enabled: bool) -> None:
        """Set free charging state via REST API."""
        if self._rest_client is None:
            raise HomeAssistantError("REST API not connected")

        self._pending_state = enabled
        self._attr_is_on = enabled
        self.async_write_ha_state()

        try:
            await self._rest_client.set_free_charging(enabled)
        except Exception as err:
            self._pending_state = None
            await self.coordinator.async_request_refresh()
            raise HomeAssistantError(f"Failed to set free charging: {err}") from err

        # Refresh REST data to get updated value
        await self.coordinator.async_request_refresh()
        self._pending_state = None
