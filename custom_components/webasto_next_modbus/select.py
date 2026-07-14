"""Select platform for Webasto Next Modbus integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WebastoConfigEntry
from .const import CONF_UNIT_ID, DOMAIN, MODEL_UNITE, UNITE_LED_DIMMING_LEVELS
from .coordinator import WebastoDataCoordinator
from .entity import WebastoRestEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WebastoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Webasto select entities."""
    runtime = entry.runtime_data

    host = entry.data[CONF_HOST]
    unit_id = entry.data[CONF_UNIT_ID]

    entities: list[SelectEntity] = []

    # The Unite's LED dimming level is an enum via REST (the Next uses a 0-100
    # brightness number instead, handled by the number platform).
    if runtime.coordinator.rest_enabled and runtime.model == MODEL_UNITE:
        entities.append(
            WebastoLedDimming(
                runtime.coordinator,
                host,
                unit_id,
                runtime.device_name,
            )
        )

    async_add_entities(entities)


class WebastoLedDimming(WebastoRestEntity, SelectEntity):
    """Select entity for the Unite's LED dimming level via REST API."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(UNITE_LED_DIMMING_LEVELS)

    def __init__(
        self,
        coordinator: WebastoDataCoordinator,
        host: str,
        unit_id: int,
        device_name: str,
    ) -> None:
        super().__init__(
            coordinator, host, unit_id, "led_dimming", device_name, coordinator.rest_client
        )
        self._pending_option: str | None = None

    def _handle_coordinator_update(self) -> None:
        """Update the current option from coordinator REST data."""

        rest_data = self.coordinator.rest_data
        current = None if rest_data is None else rest_data.led_dimming_level
        # Drop the optimistic value once the wallbox confirms it via REST.
        if self._pending_option is not None and current == self._pending_option:
            self._pending_option = None

        if self._pending_option is not None:
            self._attr_current_option = self._pending_option
        else:
            self._attr_current_option = current
        super()._handle_coordinator_update()

    async def async_select_option(self, option: str) -> None:
        """Set the LED dimming level via REST API."""
        if self._rest_client is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="rest_not_connected"
            )

        self._pending_option = option
        self._attr_current_option = option
        if self.hass is not None:
            self.async_write_ha_state()

        try:
            await self._rest_client.set_led_dimming_level(option)
        except Exception as err:
            self._pending_option = None
            if self.hass is not None:
                self._handle_coordinator_update()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_led_dimming_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        # Re-fetch the REST data now (regular polling is throttled) so the UI
        # shows the level the wallbox actually has.
        await self.coordinator.async_refresh_rest_data()
