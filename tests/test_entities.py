"""Entity platform tests for the Webasto Next Modbus integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.exceptions import HomeAssistantError

from custom_components.webasto_next_modbus.button import WebastoButton
from custom_components.webasto_next_modbus.const import (
    KEEPALIVE_TRIGGER_VALUE,
    get_register,
)
from custom_components.webasto_next_modbus.device_trigger import TRIGGER_KEEPALIVE_SENT
from custom_components.webasto_next_modbus.hub import WebastoModbusError
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

    number = WebastoNumber(coordinator, bridge, "192.0.2.11", 9, register, 32)

    await number.async_set_native_value(99)

    bridge.async_write_register.assert_awaited_with(register, register.max_value)
    coordinator.async_request_refresh.assert_awaited()


async def test_number_respects_variant_limit(coordinator_fixture) -> None:
    """Number entities should clamp to the variant-specific maximum."""

    coordinator, bridge = coordinator_fixture
    register = get_register("failsafe_current_a")
    coordinator.data = {register.key: 12}

    number = WebastoNumber(coordinator, bridge, "192.0.2.11", 9, register, 16)

    await number.async_set_native_value(99)

    bridge.async_write_register.assert_awaited_with(register, 16)
    coordinator.async_request_refresh.assert_awaited()


@pytest.mark.asyncio
async def test_number_write_failure_raises_homeassistant_error(coordinator_fixture) -> None:
    """Translate Modbus failures into HomeAssistantError for entity writes."""

    coordinator, bridge = coordinator_fixture
    register = get_register("failsafe_current_a")
    bridge.async_write_register.side_effect = WebastoModbusError("boom")

    number = WebastoNumber(coordinator, bridge, "192.0.2.11", 9, register, 32)

    with pytest.raises(HomeAssistantError):
        await number.async_set_native_value(10)


async def test_button_triggers_keepalive(coordinator_fixture) -> None:
    """Buttons should fire write-only actions."""

    coordinator, bridge = coordinator_fixture
    register = get_register("send_keepalive")

    button = WebastoButton(coordinator, bridge, "192.0.2.12", 5, register)

    with patch(
        "custom_components.webasto_next_modbus.button.async_fire_device_trigger"
    ) as fire:
        await button.async_press()

    bridge.async_write_register.assert_awaited_with(register, KEEPALIVE_TRIGGER_VALUE)
    coordinator.async_request_refresh.assert_awaited()
    fire.assert_called_once()
    args, _ = fire.call_args
    assert args[1] == "192.0.2.12-5"
    assert args[2] == TRIGGER_KEEPALIVE_SENT


async def test_session_sensors_expose_values(coordinator_fixture) -> None:
    """Session-related sensors should surface coordinator values."""

    coordinator, bridge = coordinator_fixture

    energy_register = get_register("charged_energy_wh")
    power_register = get_register("charge_power_w")

    coordinator.data = {
        energy_register.key: 480,
        power_register.key: 7200,
    }

    energy_sensor = WebastoSensor(coordinator, bridge, "198.51.100.5", 3, energy_register)
    power_sensor = WebastoSensor(coordinator, bridge, "198.51.100.5", 3, power_register)

    assert energy_sensor.native_value == 480
    assert power_sensor.native_value == 7200
    assert energy_sensor.device_class == SensorDeviceClass.ENERGY
    assert power_sensor.device_class == SensorDeviceClass.POWER


async def test_ev_max_current_sensor_available(coordinator_fixture) -> None:
    """The EV max current diagnostic sensor should expose coordinator data."""

    coordinator, bridge = coordinator_fixture
    register = get_register("ev_max_current_a")
    coordinator.data = {register.key: 26}

    sensor = WebastoSensor(coordinator, bridge, "198.51.100.6", 3, register)

    assert sensor.native_value == 26
    assert sensor.device_class == SensorDeviceClass.CURRENT


async def test_serial_number_sensor_exposes_string(coordinator_fixture) -> None:
    """String-based sensors should surface text values without modification."""

    coordinator, bridge = coordinator_fixture
    register = get_register("serial_number")
    coordinator.data = {register.key: "NEXT-000123"}

    sensor = WebastoSensor(coordinator, bridge, "203.0.113.10", 4, register)

    assert sensor.native_value == "NEXT-000123"
    assert sensor.icon == "mdi:identifier"


async def test_phase_configuration_sensor_maps_enum(coordinator_fixture) -> None:
    """Phase count sensor should expose enum labels."""

    coordinator, bridge = coordinator_fixture
    register = get_register("phase_configuration")
    coordinator.data = {register.key: 1}

    sensor = WebastoSensor(coordinator, bridge, "203.0.113.10", 4, register)

    assert sensor.native_value == "three_phase"
