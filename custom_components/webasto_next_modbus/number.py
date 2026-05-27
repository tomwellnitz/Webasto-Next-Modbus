"""Number platform for Webasto Next Modbus integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components.number import (
    NumberEntity,
    NumberExtraStoredData,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import CONF_HOST, PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WebastoConfigEntry
from .const import (
    CONF_UNIT_ID,
    SIGNAL_REGISTER_WRITTEN,
    RegisterDefinition,
    get_number_registers,
)
from .coordinator import WebastoDataCoordinator
from .entity import WebastoRegisterEntity, WebastoRestEntity
from .hub import ModbusBridge, WebastoModbusError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WebastoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Webasto number entities."""

    runtime = entry.runtime_data

    host = entry.data[CONF_HOST]
    unit_id = entry.data[CONF_UNIT_ID]

    max_current = runtime.max_current
    entities: list[NumberEntity] = [
        WebastoNumber(
            runtime.coordinator,
            runtime.bridge,
            host,
            unit_id,
            register,
            runtime.device_name,
            max_current,
        )
        for register in get_number_registers(runtime.model)
    ]

    # Add LED brightness if REST API is enabled
    if runtime.coordinator.rest_enabled:
        entities.append(
            WebastoLedBrightness(
                runtime.coordinator,
                host,
                unit_id,
                runtime.device_name,
            )
        )

    async_add_entities(entities)


class WebastoNumber(WebastoRegisterEntity, RestoreNumber, NumberEntity):
    """Expose writable Modbus registers as number entities."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: WebastoDataCoordinator,
        bridge: ModbusBridge,
        host: str,
        unit_id: int,
        register: RegisterDefinition,
        device_name: str,
        variant_max_current: int | None = None,
    ) -> None:
        super().__init__(coordinator, bridge, host, unit_id, register, device_name)

        if register.min_value is not None:
            self._attr_native_min_value = register.min_value
        if register.max_value is not None:
            self._attr_native_max_value = register.max_value
        if register.step is not None:
            self._attr_native_step = register.step
        if register.unit:
            self._attr_native_unit_of_measurement = register.unit

        self._last_written_value: int | None = None
        self._write_only = register.write_only
        if self._write_only:
            self._attr_assumed_state = True

        if coordinator.data:
            initial = coordinator.data.get(register.key)
            if not self._write_only:
                self._attr_native_value = initial
            elif initial is not None:
                try:
                    self._last_written_value = int(initial)
                except TypeError, ValueError:
                    self._last_written_value = None

        self._variant_max_current = variant_max_current
        if (
            register.key in {"failsafe_current_a", "set_current_a"}
            and variant_max_current is not None
        ):
            current_max = self._attr_native_max_value
            if current_max is None:
                current_max = float(variant_max_current)
            self._attr_native_max_value = float(min(current_max, variant_max_current))

    def _clamp_to_bounds(self, value: int) -> int:
        """Clamp an integer value to the entity's native min/max."""

        if self._attr_native_min_value is not None:
            value = max(value, int(self._attr_native_min_value))
        if self._attr_native_max_value is not None:
            value = min(value, int(self._attr_native_max_value))
        return value

    async def async_set_native_value(self, value: float) -> None:
        """Write a value to the Modbus register."""

        int_value = self._clamp_to_bounds(int(round(value)))
        await self._async_write_register(int_value)
        self._last_written_value = int_value
        self._attr_native_value = int_value
        if self.hass is not None:
            self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    def _handle_coordinator_update(self) -> None:
        """Update the native value from coordinator data."""

        if self._write_only:
            if self._last_written_value is not None:
                self._attr_native_value = self._last_written_value
            else:
                self._attr_native_value = None
        else:
            value = self.get_coordinator_value()
            self._attr_native_value = value

        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """Restore the value and subscribe to dispatcher events."""

        await super().async_added_to_hass()
        if self._write_only:
            # Show the last value we know about immediately so the entity is
            # not blank, then refine it from the wallbox in the background. The
            # Modbus read can take several seconds while the box is booting and
            # must not block platform setup.
            last_number_data = await self.async_get_last_number_data()
            if last_number_data and last_number_data.native_value is not None:
                try:
                    restored = self._clamp_to_bounds(
                        int(round(float(last_number_data.native_value)))
                    )
                    self._last_written_value = restored
                    self._attr_native_value = float(restored)
                except TypeError, ValueError:
                    _LOGGER.debug(
                        "Ignoring invalid restored value %s for %s",
                        last_number_data.native_value,
                        self.entity_id,
                    )
            if self.hass is not None and self.coordinator.config_entry is not None:
                self.coordinator.config_entry.async_create_background_task(
                    self.hass,
                    self._async_init_write_only_value(last_number_data),
                    name=f"webasto_next_modbus seed {self.entity_id}",
                )
        if self.hass is None:
            return
        remove = async_dispatcher_connect(
            self.hass,
            SIGNAL_REGISTER_WRITTEN,
            self._handle_register_written,
        )
        self.async_on_remove(remove)

    async def _async_init_write_only_value(
        self, last_number_data: NumberExtraStoredData | None
    ) -> None:
        """Seed the value from the wallbox, or re-assert the restored value."""

        if await self._async_seed_from_wallbox():
            return
        # The wallbox didn't give us the current value (e.g. it doesn't support
        # reading this register, or it's still booting): re-assert the last
        # value we set so the wallbox and the entity agree again.
        if not (last_number_data and last_number_data.native_value is not None):
            return
        try:
            restored_value = float(last_number_data.native_value)
        except TypeError, ValueError:
            return
        try:
            await self.async_set_native_value(restored_value)
        except HomeAssistantError as err:
            _LOGGER.warning(
                "Failed to re-apply %s for %s: %s",
                restored_value,
                self.entity_id,
                err,
            )

    async def _async_seed_from_wallbox(self) -> bool:
        """Seed the value from the wallbox's current register value.

        Write-only registers (e.g. the charging-current limit) aren't polled,
        so the entity would otherwise start blank on a fresh install. Reading
        the register once at startup fills it in if the wallbox answers.
        Returns ``True`` if a value was obtained.
        """
        try:
            value = await asyncio.wait_for(
                self._bridge.async_read_register(self._register), timeout=15
            )
        except WebastoModbusError, TimeoutError:
            return False
        if not isinstance(value, (int, float)):
            return False
        int_value = self._clamp_to_bounds(int(round(value)))
        self._last_written_value = int_value
        self._attr_native_value = float(int_value)
        if self.hass is not None:
            self.async_write_ha_state()
        return True

    def _handle_register_written(
        self,
        device_slug: str,
        register_key: str,
        value: int | float | None,
    ) -> None:
        """Update entity state when a service writes to the backing register."""

        if device_slug != self._unique_prefix or register_key != self.register.key:
            return
        if value is None:
            int_value: int | None = None
        else:
            try:
                int_value = int(value)
            except TypeError, ValueError:
                return
        self._last_written_value = int_value
        self._attr_native_value = int_value
        if self.hass is not None:
            self.async_write_ha_state()


class WebastoLedBrightness(WebastoRestEntity, NumberEntity):
    """Number entity for LED brightness via REST API."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:led-on"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: WebastoDataCoordinator,
        host: str,
        unit_id: int,
        device_name: str,
    ) -> None:
        super().__init__(
            coordinator, host, unit_id, "led_brightness", device_name, coordinator.rest_client
        )
        self._pending_value: int | None = None

    def _handle_coordinator_update(self) -> None:
        """Update the native value from coordinator REST data."""

        rest_data = self.coordinator.rest_data
        current = (
            None
            if rest_data is None or rest_data.led_brightness is None
            else int(rest_data.led_brightness)
        )
        # Drop the optimistic value once the wallbox confirms it via REST,
        # so a stale cached value can't bounce the slider back.
        if self._pending_value is not None and current == self._pending_value:
            self._pending_value = None

        if self._pending_value is not None:
            self._attr_native_value = float(self._pending_value)
        else:
            self._attr_native_value = None if current is None else float(current)

        super()._handle_coordinator_update()

    async def async_set_native_value(self, value: float) -> None:
        """Set LED brightness via REST API."""
        if self._rest_client is None:
            raise HomeAssistantError("REST API not connected")

        int_value = int(round(value))
        self._pending_value = int_value
        self._attr_native_value = float(int_value)
        if self.hass is not None:
            self.async_write_ha_state()

        try:
            await self._rest_client.set_led_brightness(int_value)
        except Exception as err:
            self._pending_value = None
            if self.hass is not None:
                self._handle_coordinator_update()
            raise HomeAssistantError(f"Failed to set LED brightness: {err}") from err

        # Re-fetch the REST data now (regular polling is throttled) so the UI
        # shows the value the wallbox actually has.
        await self.coordinator.async_refresh_rest_data()
