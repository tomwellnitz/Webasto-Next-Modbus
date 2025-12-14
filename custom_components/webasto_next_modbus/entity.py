"""Shared entity helpers for the Webasto Next Modbus integration."""

from __future__ import annotations

from typing import Any

from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MANUFACTURER,
    MODEL,
    RegisterDefinition,
    build_device_slug,
)
from .coordinator import WebastoDataCoordinator
from .hub import ModbusBridge, WebastoModbusError


class WebastoRegisterEntity(CoordinatorEntity[WebastoDataCoordinator]):
    """Base entity bound to a Modbus register definition."""

    def __init__(
        self,
        coordinator: WebastoDataCoordinator,
        bridge: ModbusBridge,
        host: str,
        unit_id: int,
        register: RegisterDefinition,
        device_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._bridge = bridge
        self._host = host
        self._unit_id = unit_id
        self._register = register
        self._unique_prefix = build_device_slug(host, unit_id)

        self._attr_has_entity_name = True
        self._attr_translation_key = register.translation_key or register.key
        self._attr_unique_id = f"{self._unique_prefix}-{register.key}"

        if register.icon:
            self._attr_icon = register.icon
        if register.entity_category:
            try:
                self._attr_entity_category = EntityCategory(register.entity_category)
            except ValueError:
                pass

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._unique_prefix)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=device_name,
        )

    @property
    def register(self) -> RegisterDefinition:
        """Expose the wrapped register definition."""

        return self._register

    async def _async_write_register(self, value: int) -> None:
        """Write a value to the backing Modbus register."""

        try:
            await self._bridge.async_write_register(self._register, value)
        except WebastoModbusError as err:
            raise HomeAssistantError(f"Schreibvorgang fehlgeschlagen: {err}") from err

    def get_coordinator_value(self) -> Any:
        """Helper returning the latest coordinator value for this register."""

        return self.coordinator.data.get(self._register.key)

    @property
    def available(self) -> bool | None:  # type: ignore[override]
        """Return availability aligned with Entity expectations."""

        return super().available
