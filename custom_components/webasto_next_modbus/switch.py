"""Switch platform for Webasto Next Modbus integration."""

from __future__ import annotations

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WebastoConfigEntry
from .const import CONF_UNIT_ID, RegisterDefinition, get_switch_registers
from .coordinator import WebastoDataCoordinator
from .entity import WebastoRegisterEntity, WebastoRestEntity
from .hub import ModbusBridge

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WebastoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Webasto switch entities."""
    runtime = entry.runtime_data

    host = entry.data[CONF_HOST]
    unit_id = entry.data[CONF_UNIT_ID]

    entities: list[SwitchEntity] = [
        WebastoPhaseSwitch(
            runtime.coordinator,
            runtime.bridge,
            host,
            unit_id,
            register,
            runtime.device_name,
        )
        for register in get_switch_registers(runtime.model)
    ]

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


class WebastoPhaseSwitch(WebastoRegisterEntity, SwitchEntity):
    """Switch the wallbox between single- and three-phase charging via Modbus.

    Writes the phase-switch holding register (1 = three-phase, 0 = single-phase)
    and reflects the active phase count read back from ``number_of_phases``. The
    register is undocumented and firmware-dependent, so the entity is treated as
    assumed-state.
    """

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_assumed_state = True

    _THREE_PHASE = 1
    _SINGLE_PHASE = 0

    def __init__(
        self,
        coordinator: WebastoDataCoordinator,
        bridge: ModbusBridge,
        host: str,
        unit_id: int,
        register: RegisterDefinition,
        device_name: str,
    ) -> None:
        super().__init__(coordinator, bridge, host, unit_id, register, device_name)
        self._pending_state: bool | None = None
        self._attr_is_on = self._readback_is_three_phase()

    def _readback_is_three_phase(self) -> bool | None:
        """Return the active phase mode from ``number_of_phases``, if available."""
        data = self.coordinator.data or {}
        raw = data.get("number_of_phases")
        if raw is None:
            return None
        return int(raw) == self._THREE_PHASE

    def _handle_coordinator_update(self) -> None:
        readback = self._readback_is_three_phase()
        # Drop the optimistic value once the wallbox reports the new mode.
        if self._pending_state is not None and readback == self._pending_state:
            self._pending_state = None
        if self._pending_state is not None:
            self._attr_is_on = self._pending_state
        elif readback is not None:
            self._attr_is_on = readback
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: object) -> None:
        """Switch to three-phase charging."""
        await self._async_set_phase(three_phase=True)

    async def async_turn_off(self, **kwargs: object) -> None:
        """Switch to single-phase charging."""
        await self._async_set_phase(three_phase=False)

    async def _async_set_phase(self, three_phase: bool) -> None:
        self._pending_state = three_phase
        self._attr_is_on = three_phase
        if self.hass is not None:
            self.async_write_ha_state()
        await self._async_write_register(self._THREE_PHASE if three_phase else self._SINGLE_PHASE)
        await self.coordinator.async_request_refresh()


class WebastoFreeChargingSwitch(WebastoRestEntity, SwitchEntity):
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
            coordinator, host, unit_id, "free_charging", device_name, coordinator.rest_client
        )
        self._pending_state: bool | None = None
        self._attr_is_on: bool | None = None

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        rest_data = self.coordinator.rest_data
        current = None if rest_data is None else rest_data.free_charging_enabled
        # Drop the optimistic value once the wallbox confirms it via REST.
        if self._pending_state is not None and current == self._pending_state:
            self._pending_state = None

        if self._pending_state is not None:
            self._attr_is_on = self._pending_state
        else:
            self._attr_is_on = current
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
            self._handle_coordinator_update()
            raise HomeAssistantError(f"Failed to set free charging: {err}") from err

        # Re-fetch the REST data now (regular polling is throttled) so the UI
        # shows the state the wallbox actually has.
        await self.coordinator.async_refresh_rest_data()
