"""Text platform for Webasto Next Modbus integration."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import WebastoConfigEntry
from .const import DOMAIN
from .entity import WebastoRestEntity
from .rest_client import RestClientError
from .rest_coordinator import WebastoRestCoordinator

_TAG_ID_KEY = "free_charging_tag_id"


PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WebastoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Webasto text entities."""
    runtime = entry.runtime_data

    host = entry.data[CONF_HOST]

    entities: list[TextEntity] = []

    # The free-charging tag is a REST setting (Next and Unite).
    if (rest := runtime.rest_coordinator) is not None:
        entities.append(
            WebastoFreeChargingTagIdText(
                rest,
                host,
                runtime.device_name,
                runtime.coordinator.device_model_name,
            )
        )

    async_add_entities(entities)


class WebastoFreeChargingTagIdText(WebastoRestEntity, TextEntity):
    """Text entity for Free Charging Tag ID via REST API."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = _TAG_ID_KEY

    def __init__(
        self,
        coordinator: WebastoRestCoordinator,
        host: str,
        device_name: str,
        model_name: str,
    ) -> None:
        """Initialize the text entity."""
        super().__init__(coordinator, host, _TAG_ID_KEY, device_name, model_name)

    @property
    def native_value(self) -> str | None:
        """Return the current value."""
        if not self.rest_data:
            return None
        return self.rest_data.free_charging_tag_id

    async def async_set_value(self, value: str) -> None:
        """Set the text value."""

        try:
            await self.rest_client.set_free_charging_tag_id(value)
        except (RestClientError, ValueError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_tag_id_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        # Regular REST polling is throttled; re-fetch now so the entity reflects
        # what the wallbox actually stored instead of the stale cached value.
        await self.coordinator.async_refresh_after_write()
