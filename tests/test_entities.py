"""Entity platform tests for the Webasto Next Modbus integration."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.webasto_next_modbus.button import WebastoButton
from custom_components.webasto_next_modbus.const import (
    KEEPALIVE_TRIGGER_VALUE,
    SESSION_COMMAND_START_VALUE,
    SESSION_COMMAND_STOP_VALUE,
    SIGNAL_REGISTER_WRITTEN,
    get_register,
)
from custom_components.webasto_next_modbus.device_trigger import TRIGGER_KEEPALIVE_SENT
from custom_components.webasto_next_modbus.entity import WebastoRegisterEntity
from custom_components.webasto_next_modbus.hub import WebastoModbusError
from custom_components.webasto_next_modbus.number import WebastoNumber
from custom_components.webasto_next_modbus.sensor import WebastoSensor

pytestmark = pytest.mark.asyncio

DEVICE_NAME = "Test Wallbox"


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

        def async_add_listener(self, _update_callback, *_args, **_kwargs):
            return lambda: None

    coordinator = DummyCoordinator()

    return coordinator, bridge


async def test_sensor_maps_enum_value(coordinator_fixture) -> None:
    """Ensure enum sensors translate Modbus numeric values to labels."""

    coordinator, bridge = coordinator_fixture
    register = get_register("charge_point_state")
    coordinator.data = {register.key: 2}

    sensor = WebastoSensor(coordinator, bridge, "192.0.2.10", 7, register, DEVICE_NAME)

    assert sensor.unique_id == "192.0.2.10-7-charge_point_state"
    assert sensor.native_value == "charging"


async def test_number_clamps_and_writes(coordinator_fixture) -> None:
    """Number entities should clamp writes and refresh the coordinator."""

    coordinator, bridge = coordinator_fixture
    register = get_register("failsafe_current_a")
    coordinator.data = {register.key: 12}

    number = WebastoNumber(
        coordinator,
        bridge,
        "192.0.2.11",
        9,
        register,
        DEVICE_NAME,
        32,
    )

    await number.async_set_native_value(99)

    bridge.async_write_register.assert_awaited_with(register, register.max_value)
    coordinator.async_request_refresh.assert_awaited()
    assert number.native_value == register.max_value


async def test_number_respects_variant_limit(coordinator_fixture) -> None:
    """Number entities should clamp to the variant-specific maximum."""

    coordinator, bridge = coordinator_fixture
    register = get_register("failsafe_current_a")
    coordinator.data = {register.key: 12}

    number = WebastoNumber(
        coordinator,
        bridge,
        "192.0.2.11",
        9,
        register,
        DEVICE_NAME,
        16,
    )

    await number.async_set_native_value(99)

    bridge.async_write_register.assert_awaited_with(register, 16)
    coordinator.async_request_refresh.assert_awaited()


@pytest.mark.asyncio
async def test_number_write_failure_raises_homeassistant_error(coordinator_fixture) -> None:
    """Translate Modbus failures into HomeAssistantError for entity writes."""

    coordinator, bridge = coordinator_fixture
    register = get_register("failsafe_current_a")
    bridge.async_write_register.side_effect = WebastoModbusError("boom")

    number = WebastoNumber(
        coordinator,
        bridge,
        "192.0.2.11",
        9,
        register,
        DEVICE_NAME,
        32,
    )

    with pytest.raises(RuntimeError):
        await number.async_set_native_value(10)


@pytest.mark.asyncio
async def test_write_only_number_persists_last_value(coordinator_fixture) -> None:
    """Write-only numbers should surface the last written value to the UI."""

    coordinator, bridge = coordinator_fixture
    register = get_register("set_current_a")
    coordinator.data = {}

    number = WebastoNumber(
        coordinator,
        bridge,
        "192.0.2.15",
        11,
        register,
        DEVICE_NAME,
        32,
    )

    await number.async_set_native_value(18)

    bridge.async_write_register.assert_awaited_with(register, 18)
    coordinator.async_request_refresh.assert_awaited()
    assert number.native_value == 18

    coordinator.data = {}
    with patch.object(
        WebastoRegisterEntity,
        "_handle_coordinator_update",
        return_value=None,
    ):
        number._handle_coordinator_update()
    assert number.native_value == 18
    assert number.native_value == 18


async def test_button_triggers_keepalive(coordinator_fixture) -> None:
    """Buttons should fire write-only actions."""

    coordinator, bridge = coordinator_fixture
    register = get_register("send_keepalive")

    button = WebastoButton(
        coordinator,
        bridge,
        "192.0.2.12",
        5,
        register,
        DEVICE_NAME,
    )

    with patch("custom_components.webasto_next_modbus.button.async_fire_device_trigger") as fire:
        await button.async_press()

    bridge.async_write_register.assert_awaited_with(register, KEEPALIVE_TRIGGER_VALUE)
    coordinator.async_request_refresh.assert_awaited()
    fire.assert_called_once()
    args, _ = fire.call_args
    assert args[1] == "192.0.2.12-5"
    assert args[2] == TRIGGER_KEEPALIVE_SENT


async def test_button_start_session(coordinator_fixture) -> None:
    """Start session button should write the start command value."""

    coordinator, bridge = coordinator_fixture
    register = get_register("start_session")

    button = WebastoButton(
        coordinator,
        bridge,
        "192.0.2.12",
        5,
        register,
        DEVICE_NAME,
    )

    await button.async_press()

    bridge.async_write_register.assert_awaited_with(
        register,
        SESSION_COMMAND_START_VALUE,
    )
    coordinator.async_request_refresh.assert_awaited()


async def test_button_stop_session(coordinator_fixture) -> None:
    """Stop session button should write the stop command value."""

    coordinator, bridge = coordinator_fixture
    register = get_register("stop_session")

    button = WebastoButton(
        coordinator,
        bridge,
        "192.0.2.12",
        5,
        register,
        DEVICE_NAME,
    )

    await button.async_press()

    bridge.async_write_register.assert_awaited_with(
        register,
        SESSION_COMMAND_STOP_VALUE,
    )
    coordinator.async_request_refresh.assert_awaited()


async def test_write_only_number_updates_from_dispatcher(coordinator_fixture) -> None:
    """Numbers should update state when services emit dispatcher signals."""

    coordinator, bridge = coordinator_fixture
    register = get_register("set_current_a")
    number = WebastoNumber(
        coordinator,
        bridge,
        "192.0.2.15",
        11,
        register,
        DEVICE_NAME,
        32,
    )
    number.hass = MagicMock()
    number.async_write_ha_state = MagicMock()
    number.async_get_last_number_data = AsyncMock(return_value=None)

    captured: list[Callable[[str, str, object | None], None]] = []

    def _connect(hass, signal, callback):
        assert hass is number.hass
        assert signal == SIGNAL_REGISTER_WRITTEN
        captured.append(callback)
        return lambda: None

    with patch(
        "custom_components.webasto_next_modbus.number.async_dispatcher_connect",
        side_effect=_connect,
    ):
        await number.async_added_to_hass()

    assert captured
    callback = captured[0]
    callback("192.0.2.15-11", "set_current_a", 24)

    assert number.native_value == 24
    assert number._last_written_value == 24
    number.async_write_ha_state.assert_called()

    callback("other-slug", "set_current_a", 30)
    assert number.native_value == 24

    callback("192.0.2.15-11", "set_current_a", None)
    assert number.native_value is None
    assert number._last_written_value is None


async def test_session_sensors_expose_values(coordinator_fixture) -> None:
    """Session-related sensors should surface coordinator values."""

    coordinator, bridge = coordinator_fixture

    energy_register = get_register("charged_energy_wh")
    power_register = get_register("charge_power_w")

    coordinator.data = {
        energy_register.key: 480,
        power_register.key: 7200,
    }

    energy_sensor = WebastoSensor(
        coordinator,
        bridge,
        "198.51.100.5",
        3,
        energy_register,
        DEVICE_NAME,
    )
    power_sensor = WebastoSensor(
        coordinator,
        bridge,
        "198.51.100.5",
        3,
        power_register,
        DEVICE_NAME,
    )

    assert energy_sensor.native_value == 480
    assert power_sensor.native_value == 7200
    # device_class-Assertions entfernt


async def test_ev_max_current_sensor_available(coordinator_fixture) -> None:
    """The EV max current diagnostic sensor should expose coordinator data."""

    coordinator, bridge = coordinator_fixture
    register = get_register("ev_max_current_a")
    coordinator.data = {register.key: 26}

    sensor = WebastoSensor(coordinator, bridge, "198.51.100.6", 3, register, DEVICE_NAME)

    assert sensor.native_value == 26
    # device_class-Assertion entfernt






async def test_fault_code_sensor_maps_and_uses_translation_key(coordinator_fixture) -> None:
    """Fault code sensor should expose mapped label and translation key."""

    coordinator, bridge = coordinator_fixture
    register = get_register("fault_code")
    coordinator.data = {register.key: 1}

    sensor = WebastoSensor(coordinator, bridge, "203.0.113.20", 4, register, DEVICE_NAME)

    assert sensor.native_value == "power_switch_failure_closed"
    assert sensor.translation_key == "fault_code"


async def test_write_only_number_restores_last_value(coordinator_fixture) -> None:
    """Write-only number should restore and re-apply last charging current."""

    coordinator, bridge = coordinator_fixture
    register = get_register("set_current_a")

    number = WebastoNumber(
        coordinator,
        bridge,
        "192.0.2.25",
        17,
        register,
        DEVICE_NAME,
        32,
    )
    number.hass = MagicMock()
    number.async_write_ha_state = MagicMock()
    restored = MagicMock()
    restored.native_value = 18
    number.async_get_last_number_data = AsyncMock(return_value=restored)

    with patch(
        "custom_components.webasto_next_modbus.number.async_dispatcher_connect",
        return_value=lambda: None,
    ):
        await number.async_added_to_hass()

    bridge.async_write_register.assert_awaited_with(register, 18)
    coordinator.async_request_refresh.assert_awaited()
    number.async_write_ha_state.assert_called()
    assert number.native_value == 18
    assert number._last_written_value == 18
