"""Text platform for Webasto Next Modbus integration."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
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
    """Set up Webasto text entities."""
    runtime: RuntimeData = hass.data[DOMAIN][entry.entry_id]

    host = entry.data[CONF_HOST]
    unit_id = entry.data[CONF_UNIT_ID]

    entities: list[TextEntity] = []

    # Add Free Charging Tag ID text entity if REST API is enabled
    if runtime.coordinator.rest_enabled:
        entities.append(
            WebastoFreeChargingTagIdText(
                runtime.coordinator,
                host,
                unit_id,
                runtime.device_name,
            )
        )

    async_add_entities(entities)


class WebastoFreeChargingTagIdText(WebastoRestEntity, TextEntity):  # type: ignore[misc]
    """Text entity for Free Charging Tag ID via REST API."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "free_charging_tag_id"

    def __init__(
        self,
        coordinator: WebastoDataCoordinator,
        host: str,
        unit_id: int,
        device_name: str,
    ) -> None:
        """Initialize the text entity."""
        super().__init__(coordinator, host, unit_id, "free_charging_tag_id", device_name)
        self._attr_unique_id = f"{host}_{unit_id}_free_charging_tag_id"

    @property
    def native_value(self) -> str | None:
        """Return the current value."""
        return self.coordinator.data.get("free_charging_tag_id")

    async def async_set_value(self, value: str) -> None:
        """Set the text value."""
        if not self.coordinator.rest_client:
            return

        try:
            await self.coordinator.rest_client.set_free_charging_tag_id(value)
            await self.coordinator.async_request_refresh()
        except Exception as err:
            raise HomeAssistantError(f"Failed to set free charging tag ID: {err}") from err
