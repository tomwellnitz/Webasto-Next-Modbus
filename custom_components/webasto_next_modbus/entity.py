"""Shared entity helpers for the Webasto Next Modbus integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from .rest_client import RestClient


def build_device_info(
    unique_prefix: str,
    device_name: str,
    coordinator: WebastoDataCoordinator,
) -> DeviceInfo:
    """Build DeviceInfo with optional REST data."""
    device_info = DeviceInfo(
        identifiers={(DOMAIN, unique_prefix)},
        manufacturer=MANUFACTURER,
        model=MODEL,
        name=device_name,
    )

    # Add REST data if available
    rest_data = coordinator.rest_data
    if rest_data is not None:
        if rest_data.comboard_sw_version:
            device_info["sw_version"] = rest_data.comboard_sw_version
        if rest_data.comboard_hw_version:
            device_info["hw_version"] = rest_data.comboard_hw_version
        if rest_data.ip_address:
            device_info["configuration_url"] = f"https://{rest_data.ip_address}"
        # MAC addresses stored in connections
        connections: set[tuple[str, str]] = set()
        if rest_data.mac_address_ethernet:
            connections.add(("mac", rest_data.mac_address_ethernet.lower()))
        if rest_data.mac_address_wifi:
            connections.add(("mac", rest_data.mac_address_wifi.lower()))
        if connections:
            device_info["connections"] = connections

    return device_info


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
        self._device_name = device_name

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

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info with optional REST data."""
        return build_device_info(self._unique_prefix, self._device_name, self.coordinator)

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


class WebastoRestEntity(CoordinatorEntity[WebastoDataCoordinator]):
    """Base entity for REST API data."""

    def __init__(
        self,
        coordinator: WebastoDataCoordinator,
        host: str,
        unit_id: int,
        entity_key: str,
        device_name: str,
        rest_client: RestClient | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._host = host
        self._unit_id = unit_id
        self._entity_key = entity_key
        self._unique_prefix = build_device_slug(host, unit_id)
        self._device_name = device_name
        self._rest_client = rest_client

        self._attr_has_entity_name = True
        self._attr_translation_key = entity_key
        self._attr_unique_id = f"{self._unique_prefix}-rest-{entity_key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info with optional REST data."""
        return build_device_info(self._unique_prefix, self._device_name, self.coordinator)

    @property
    def available(self) -> bool:
        """Return True if REST data is available."""
        return self.coordinator.rest_enabled and self.coordinator.rest_data is not None
