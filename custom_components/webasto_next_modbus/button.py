"""Button platform for Webasto Next Modbus integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import WebastoConfigEntry
from .const import (
    CONF_UNIT_ID,
    DOMAIN,
    KEEPALIVE_TRIGGER_VALUE,
    SESSION_COMMAND_START_VALUE,
    SESSION_COMMAND_STOP_VALUE,
    get_button_registers,
)
from .device_trigger import TRIGGER_KEEPALIVE_SENT, async_fire_device_trigger
from .entity import WebastoRegisterEntity, WebastoRestEntity
from .hub import WebastoModbusError
from .rest_client import RestClientError
from .rest_coordinator import WebastoRestCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WebastoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Webasto button entities."""

    runtime = entry.runtime_data

    host = entry.data[CONF_HOST]
    unit_id = entry.data[CONF_UNIT_ID]

    entities: list[ButtonEntity] = [
        WebastoButton(
            runtime.coordinator,
            runtime.bridge,
            host,
            unit_id,
            register,
            runtime.device_name,
        )
        for register in get_button_registers(runtime.model)
    ]

    # Restart is a REST action (Next and Unite).
    if (rest := runtime.rest_coordinator) is not None:
        entities.append(
            WebastoRestartButton(
                rest,
                host,
                unit_id,
                runtime.device_name,
                runtime.coordinator.device_model_name,
            )
        )

    async_add_entities(entities)


class WebastoButton(WebastoRegisterEntity, ButtonEntity):
    """Represent write-only Modbus actions as buttons."""

    _attr_has_entity_name = True

    async def async_press(self) -> None:
        """Trigger the Modbus action associated with the register."""

        if self.register.key == "start_session":
            await self._async_send_session_command(SESSION_COMMAND_START_VALUE)
        elif self.register.key == "stop_session":
            await self._async_send_session_command(SESSION_COMMAND_STOP_VALUE)
        else:
            await self._async_write_register(KEEPALIVE_TRIGGER_VALUE)
        if self.register.key == "send_keepalive":
            async_fire_device_trigger(
                self.coordinator.hass,
                self._unique_prefix,
                TRIGGER_KEEPALIVE_SENT,
                {"source": "button"},
            )
        await self.coordinator.async_request_refresh()

    async def _async_send_session_command(self, value: int) -> None:
        try:
            await self._bridge.async_send_session_command(value)
        except WebastoModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err


class WebastoRestartButton(WebastoRestEntity, ButtonEntity):
    """Button to restart the wallbox via REST API."""

    _attr_has_entity_name = True
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: WebastoRestCoordinator,
        host: str,
        unit_id: int,
        device_name: str,
        model_name: str,
    ) -> None:
        super().__init__(coordinator, host, unit_id, "restart_system", device_name, model_name)

    async def async_press(self) -> None:
        """Restart the wallbox via REST API."""

        try:
            await self.rest_client.restart_system()
        except (RestClientError, ValueError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="restart_failed",
                translation_placeholders={"error": str(err)},
            ) from err
