"""Text platform for Webasto Next Modbus integration."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import WebastoConfigEntry
from .const import CONF_UNIT_ID, DOMAIN, build_device_slug
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
    unit_id = entry.data[CONF_UNIT_ID]

    entities: list[TextEntity] = []

    # The free-charging tag is a REST setting (Next and Unite).
    if (rest := runtime.rest_coordinator) is not None:
        _migrate_tag_id_unique_id(hass, host, unit_id)
        entities.append(
            WebastoFreeChargingTagIdText(
                rest,
                host,
                unit_id,
                runtime.device_name,
                runtime.coordinator.device_model_name,
            )
        )

    async_add_entities(entities)


def _migrate_tag_id_unique_id(hass: HomeAssistant, host: str, unit_id: int) -> None:
    """Migrate the pre-1.1.7 tag-id unique_id to the shared REST-entity scheme."""

    new_uid = f"{build_device_slug(host, unit_id)}-rest-{_TAG_ID_KEY}"
    old_uid = f"{host}_{unit_id}_{_TAG_ID_KEY}"
    if old_uid == new_uid:
        return
    registry = er.async_get(hass)
    old_entity_id = registry.async_get_entity_id("text", DOMAIN, old_uid)
    if old_entity_id and registry.async_get_entity_id("text", DOMAIN, new_uid) is None:
        registry.async_update_entity(old_entity_id, new_unique_id=new_uid)


class WebastoFreeChargingTagIdText(WebastoRestEntity, TextEntity):
    """Text entity for Free Charging Tag ID via REST API."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = _TAG_ID_KEY

    def __init__(
        self,
        coordinator: WebastoRestCoordinator,
        host: str,
        unit_id: int,
        device_name: str,
        model_name: str,
    ) -> None:
        """Initialize the text entity."""
        super().__init__(coordinator, host, unit_id, _TAG_ID_KEY, device_name, model_name)

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
