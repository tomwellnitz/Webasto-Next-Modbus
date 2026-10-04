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
)
from .coordinator import WebastoDataCoordinator
from .hub import ModbusBridge, WebastoModbusError
from .rest_client import RestClient, RestData
from .rest_coordinator import WebastoRestCoordinator


def build_device_info(
    unique_prefix: str,
    device_name: str,
    model_name: str,
    host: str,
) -> DeviceInfo:
    """Build the DeviceInfo shared by all entities of a wallbox.

    Firmware/hardware versions and MAC addresses come from the REST API and
    are pushed to the device registry by the REST coordinator once known.
    """
    url_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return DeviceInfo(
        identifiers={(DOMAIN, unique_prefix)},
        manufacturer=MANUFACTURER,
        model=model_name or MODEL,
        name=device_name,
        configuration_url=f"https://{url_host}",
    )


class WebastoRegisterEntity(CoordinatorEntity[WebastoDataCoordinator]):
    """Base entity bound to a Modbus register definition."""

    def __init__(
        self,
        coordinator: WebastoDataCoordinator,
        bridge: ModbusBridge,
        host: str,
        register: RegisterDefinition,
        device_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._bridge = bridge
        self._register = register
        self._unique_prefix = coordinator.device_slug
        self._device_name = device_name

        self._attr_has_entity_name = True
        self._attr_translation_key = register.translation_key or register.key
        self._attr_unique_id = f"{self._unique_prefix}-{register.key}"
        self._attr_device_info = build_device_info(
            self._unique_prefix, self._device_name, coordinator.device_model_name, host
        )

        if register.entity_category:
            try:
                self._attr_entity_category = EntityCategory(register.entity_category)
            except ValueError:
                pass
        self._attr_entity_registry_enabled_default = register.entity_registry_enabled_default

    @property
    def register(self) -> RegisterDefinition:
        """Expose the wrapped register definition."""

        return self._register

    async def _async_write_register(self, value: int) -> None:
        """Write a value to the backing Modbus register."""

        try:
            await self._bridge.async_write_register(self._register, value)
        except WebastoModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err

    def get_coordinator_value(self) -> Any:
        """Helper returning the latest coordinator value for this register."""

        return self.coordinator.data.get(self._register.key)


class WebastoRestEntity(CoordinatorEntity[WebastoRestCoordinator]):
    """Base entity for data from the optional REST API."""

    def __init__(
        self,
        coordinator: WebastoRestCoordinator,
        host: str,
        entity_key: str,
        device_name: str,
        model_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._entity_key = entity_key
        self._unique_prefix = coordinator.device_slug
        self._device_name = device_name

        self._attr_has_entity_name = True
        self._attr_translation_key = entity_key
        self._attr_unique_id = f"{self._unique_prefix}-rest-{entity_key}"
        self._attr_device_info = build_device_info(
            self._unique_prefix, self._device_name, model_name, host
        )

    @property
    def rest_data(self) -> RestData | None:
        """Return the latest REST data, if any was fetched yet."""
        return self.coordinator.data

    @property
    def rest_client(self) -> RestClient:
        """Return the REST client used for writes."""
        return self.coordinator.client

    @property
    def available(self) -> bool:
        """Available while the last REST poll succeeded and data exists."""
        return super().available and self.coordinator.data is not None
