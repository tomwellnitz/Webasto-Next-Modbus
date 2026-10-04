"""Select platform for Webasto Next Modbus integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import WebastoConfigEntry
from .const import (
    CONF_UNIT_ID,
    DOMAIN,
    MODEL_UNITE,
    UNITE_LED_DIMMING_API_TO_OPTION,
    UNITE_LED_DIMMING_OPTION_TO_API,
)
from .entity import WebastoRestEntity
from .rest_client import RestClientError
from .rest_coordinator import WebastoRestCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WebastoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Webasto select entities."""
    runtime = entry.runtime_data

    host = entry.data[CONF_HOST]
    unit_id = entry.data[CONF_UNIT_ID]

    entities: list[SelectEntity] = []

    # The Unite's LED dimming level is an enum via REST (the Next uses a 0-100
    # brightness number instead, handled by the number platform).
    if (rest := runtime.rest_coordinator) is not None and runtime.model == MODEL_UNITE:
        entities.append(
            WebastoLedDimming(
                rest,
                host,
                unit_id,
                runtime.device_name,
                runtime.coordinator.device_model_name,
            )
        )

    async_add_entities(entities)


class WebastoLedDimming(WebastoRestEntity, SelectEntity):
    """Select entity for the Unite's LED dimming level via REST API."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    # HA-facing options are lowercase slugs (translation keys must be); the
    # wallbox's camelCase API values are mapped in/out below.
    _attr_options = list(UNITE_LED_DIMMING_OPTION_TO_API)

    def __init__(
        self,
        coordinator: WebastoRestCoordinator,
        host: str,
        unit_id: int,
        device_name: str,
        model_name: str,
    ) -> None:
        super().__init__(coordinator, host, unit_id, "led_dimming", device_name, model_name)
        self._pending_option: str | None = None
        self._update_from_rest()

    def _update_from_rest(self) -> None:
        """Derive the state from the latest REST data."""

        rest_data = self.rest_data
        api_value = None if rest_data is None else rest_data.led_dimming_level
        current = UNITE_LED_DIMMING_API_TO_OPTION.get(api_value) if api_value else None
        # Drop the optimistic value once the wallbox confirms it via REST.
        if self._pending_option is not None and current == self._pending_option:
            self._pending_option = None

        if self._pending_option is not None:
            self._attr_current_option = self._pending_option
        else:
            self._attr_current_option = current

    def _handle_coordinator_update(self) -> None:
        self._update_from_rest()
        super()._handle_coordinator_update()

    async def async_select_option(self, option: str) -> None:
        """Set the LED dimming level via REST API."""

        self._pending_option = option
        self._attr_current_option = option
        if self.hass is not None:
            self.async_write_ha_state()

        try:
            await self.rest_client.set_led_dimming_level(UNITE_LED_DIMMING_OPTION_TO_API[option])
        except (RestClientError, ValueError) as err:
            self._pending_option = None
            self._update_from_rest()
            if self.hass is not None:
                self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_led_dimming_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        # Re-fetch the REST data now (regular polling is throttled) so the UI
        # shows the level the wallbox actually has.
        await self.coordinator.async_refresh_after_write()
