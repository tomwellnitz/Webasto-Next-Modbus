"""Entity platform tests for the Webasto Next Modbus integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.webasto_next_modbus.button import WebastoButton
from custom_components.webasto_next_modbus.const import (
    KEEPALIVE_TRIGGER_VALUE,
    get_register,
)
from custom_components.webasto_next_modbus.number import WebastoNumber
from custom_components.webasto_next_modbus.sensor import WebastoSensor

pytestmark = pytest.mark.asyncio


@pytest.fixture
def coordinator_fixture():
    """Yield a coordinator and bridge pair for entity tests."""

    bridge = AsyncMock()
    bridge.async_write_register = AsyncMock()

    class DummyCoordinator:
        def __init__(self) -> None:
            self.data: dict[str, object] = {}
            self.async_request_refresh = AsyncMock()
            self.hass = MagicMock()

        def async_add_listener(self, _update_callback):
            return lambda: None

    coordinator = DummyCoordinator()

    return coordinator, bridge


async def test_sensor_maps_enum_value(coordinator_fixture) -> None:
    """Ensure enum sensors translate Modbus numeric values to labels."""

    coordinator, bridge = coordinator_fixture
    register = get_register("charge_point_state")
    coordinator.data = {register.key: 2}

    sensor = WebastoSensor(coordinator, bridge, "192.0.2.10", 7, register)

    assert sensor.unique_id == "192.0.2.10-7-charge_point_state"
    assert sensor.native_value == "charging"


async def test_number_clamps_and_writes(coordinator_fixture) -> None:
    """Number entities should clamp writes and refresh the coordinator."""

    coordinator, bridge = coordinator_fixture
    register = get_register("failsafe_current_a")
    coordinator.data = {register.key: 12}

    number = WebastoNumber(coordinator, bridge, "192.0.2.11", 9, register)

    await number.async_set_native_value(99)

    bridge.async_write_register.assert_awaited_with(register, register.max_value)
    coordinator.async_request_refresh.assert_awaited()


async def test_button_triggers_keepalive(coordinator_fixture) -> None:
    """Buttons should fire write-only actions."""

    coordinator, bridge = coordinator_fixture
    register = get_register("send_keepalive")

    button = WebastoButton(coordinator, bridge, "192.0.2.12", 5, register)

    await button.async_press()

    bridge.async_write_register.assert_awaited_with(register, KEEPALIVE_TRIGGER_VALUE)
    coordinator.async_request_refresh.assert_awaited()
