"""Entity platform tests for the Webasto Next Modbus integration."""

from __future__ import annotations

import asyncio
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

    class DummyConfigEntry:
        def __init__(self) -> None:
            self.background_tasks: list[asyncio.Future] = []

        def async_create_background_task(self, _hass, target, *_args, **_kwargs):
            task = asyncio.ensure_future(target)
            self.background_tasks.append(task)
            return task

    class DummyCoordinator:
        def __init__(self) -> None:
            self.data: dict[str, object] = {}
            self.rest_data = None
            self.async_request_refresh = AsyncMock()
            self.hass = MagicMock()
            self.config_entry = DummyConfigEntry()

        def async_add_listener(self, _update_callback, *_args, **_kwargs):
            return lambda: None

    coordinator = DummyCoordinator()

    return coordinator, bridge


async def _drain_background_tasks(coordinator) -> None:
    """Run any background tasks the entity scheduled to completion."""

    for task in list(coordinator.config_entry.background_tasks):
        await task


async def test_sensor_maps_enum_value(coordinator_fixture) -> None:
    """Ensure enum sensors translate Modbus numeric values to labels."""

    coordinator, bridge = coordinator_fixture
    register = get_register("charge_point_state")
    coordinator.data = {register.key: 3}

    sensor = WebastoSensor(coordinator, bridge, "192.0.2.10", 7, register, DEVICE_NAME)

    assert sensor.unique_id == "192.0.2.10-7-charge_point_state"
    assert sensor.native_value == "charging"


async def test_entity_has_correct_translation_attributes(coordinator_fixture) -> None:
    """Ensure entities have has_entity_name set and correct translation key."""
    coordinator, bridge = coordinator_fixture
    register = get_register("charge_point_state")

    sensor = WebastoSensor(coordinator, bridge, "192.0.2.10", 7, register, DEVICE_NAME)

    assert sensor.has_entity_name is True
    assert sensor.translation_key == "charge_point_state"
    # Name should be None or handled by HA when has_entity_name is True
    # In our implementation we removed _attr_name, so name property might behave differently
    # depending on base class, but usually it returns None if _attr_name is not set
    # and has_entity_name is True (HA constructs it).
    # Let's check _attr_name is not set or None
    assert not hasattr(sensor, "_attr_name") or sensor._attr_name is None


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

    from homeassistant.exceptions import HomeAssistantError

    with pytest.raises(HomeAssistantError):
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

    await _drain_background_tasks(coordinator)


async def test_session_sensors_expose_values(coordinator_fixture) -> None:
    """Session-related sensors should surface coordinator values."""

    coordinator, bridge = coordinator_fixture

    energy_register = get_register("charged_energy_wh")

    coordinator.data = {
        energy_register.key: 480,
    }

    energy_sensor = WebastoSensor(
        coordinator,
        bridge,
        "198.51.100.5",
        3,
        energy_register,
        DEVICE_NAME,
    )

    assert energy_sensor.native_value == 480
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

    assert sensor.native_value == "power_switch_failure"
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
        await _drain_background_tasks(coordinator)

    bridge.async_write_register.assert_awaited_with(register, 18)
    coordinator.async_request_refresh.assert_awaited()
    number.async_write_ha_state.assert_called()
    assert number.native_value == 18
    assert number._last_written_value == 18


async def test_write_only_number_seeds_from_wallbox(coordinator_fixture) -> None:
    """A write-only number reads its current value from the wallbox on add."""

    coordinator, bridge = coordinator_fixture
    register = get_register("set_current_a")
    bridge.async_read_register = AsyncMock(return_value=16)

    number = WebastoNumber(coordinator, bridge, "192.0.2.30", 9, register, DEVICE_NAME, 32)
    number.hass = MagicMock()
    number.async_write_ha_state = MagicMock()
    number.async_get_last_number_data = AsyncMock(return_value=MagicMock(native_value=24))

    with patch(
        "custom_components.webasto_next_modbus.number.async_dispatcher_connect",
        return_value=lambda: None,
    ):
        await number.async_added_to_hass()
        await _drain_background_tasks(coordinator)

    assert number.native_value == 16
    assert number._last_written_value == 16
    # The wallbox value wins over the restored value, and the re-apply
    # fallback (which would write back) is not used.
    bridge.async_write_register.assert_not_awaited()


async def test_connectivity_binary_sensor(coordinator_fixture) -> None:
    """The connectivity sensor stays available and tracks last_update_success."""

    from custom_components.webasto_next_modbus.binary_sensor import WebastoConnectivitySensor

    coordinator, _bridge = coordinator_fixture
    coordinator.last_update_success = True

    sensor = WebastoConnectivitySensor(coordinator, "192.0.2.40", 3, DEVICE_NAME)

    assert sensor.unique_id == "192.0.2.40-3-connected"
    assert sensor.translation_key == "connected"
    assert sensor.available is True
    assert sensor.is_on is True

    coordinator.last_update_success = False
    assert sensor.available is True
    assert sensor.is_on is False


async def test_led_brightness_does_not_revert_to_stale_value(coordinator_fixture) -> None:
    """Setting LED brightness forces a REST refresh and isn't bounced back by stale cache."""

    from custom_components.webasto_next_modbus.number import WebastoLedBrightness

    coordinator, _bridge = coordinator_fixture
    coordinator.rest_enabled = True
    coordinator.rest_data = MagicMock(
        led_brightness=19,
        comboard_sw_version=None,
        comboard_hw_version=None,
        ip_address=None,
        mac_address_ethernet=None,
        mac_address_wifi=None,
    )
    coordinator.rest_client = MagicMock()
    coordinator.rest_client.set_led_brightness = AsyncMock()

    led = WebastoLedBrightness(coordinator, "192.0.2.50", 3, DEVICE_NAME)
    led.hass = MagicMock()
    led.async_write_ha_state = MagicMock()

    async def _refresh() -> None:
        # The wallbox now reports the value we just set.
        coordinator.rest_data = MagicMock(
            led_brightness=5,
            comboard_sw_version=None,
            comboard_hw_version=None,
            ip_address=None,
            mac_address_ethernet=None,
            mac_address_wifi=None,
        )
        led._handle_coordinator_update()

    coordinator.async_refresh_rest_data = _refresh

    await led.async_set_native_value(5)

    coordinator.rest_client.set_led_brightness.assert_awaited_once_with(5)
    assert led.native_value == 5
    assert led._pending_value is None
    # A later coordinator poll with the (still-correct) value must not revert it.
    led._handle_coordinator_update()
    assert led.native_value == 5


async def test_free_charging_switch_does_not_revert_to_stale_value(coordinator_fixture) -> None:
    """Toggling free charging forces a REST refresh and isn't bounced back by stale cache."""

    from custom_components.webasto_next_modbus.switch import WebastoFreeChargingSwitch

    def _rest_data(enabled):
        return MagicMock(
            free_charging_enabled=enabled,
            comboard_sw_version=None,
            comboard_hw_version=None,
            ip_address=None,
            mac_address_ethernet=None,
            mac_address_wifi=None,
        )

    coordinator, _bridge = coordinator_fixture
    coordinator.rest_enabled = True
    coordinator.rest_data = _rest_data(False)
    coordinator.rest_client = MagicMock()
    coordinator.rest_client.set_free_charging = AsyncMock()

    switch = WebastoFreeChargingSwitch(coordinator, "192.0.2.51", 3, DEVICE_NAME)
    switch.hass = MagicMock()
    switch.async_write_ha_state = MagicMock()

    async def _refresh() -> None:
        coordinator.rest_data = _rest_data(True)
        switch._handle_coordinator_update()

    coordinator.async_refresh_rest_data = _refresh

    await switch.async_turn_on()

    coordinator.rest_client.set_free_charging.assert_awaited_once_with(True)
    assert switch.is_on is True
    assert switch._pending_state is None
    switch._handle_coordinator_update()
    assert switch.is_on is True


async def test_phase_switch_writes_and_reads_back(coordinator_fixture) -> None:
    """The Unite phase switch writes register 405 and reflects number_of_phases."""

    from custom_components.webasto_next_modbus.const import UNITE_PHASE_SWITCH_REGISTER
    from custom_components.webasto_next_modbus.switch import WebastoPhaseSwitch

    coordinator, bridge = coordinator_fixture
    coordinator.data = {"number_of_phases": 0}

    switch = WebastoPhaseSwitch(
        coordinator, bridge, "192.0.2.60", 255, UNITE_PHASE_SWITCH_REGISTER, DEVICE_NAME
    )
    switch.hass = MagicMock()
    switch.async_write_ha_state = MagicMock()

    assert switch.is_on is False  # single-phase

    await switch.async_turn_on()
    bridge.async_write_register.assert_awaited_with(UNITE_PHASE_SWITCH_REGISTER, 1)
    coordinator.async_request_refresh.assert_awaited()
    assert switch.is_on is True

    # The wallbox confirms three-phase -> the optimistic value is dropped.
    coordinator.data = {"number_of_phases": 1}
    switch._handle_coordinator_update()
    assert switch.is_on is True
    assert switch._pending_state is None

    # A later real read back to single-phase is reflected.
    coordinator.data = {"number_of_phases": 0}
    switch._handle_coordinator_update()
    assert switch.is_on is False


async def test_phase_switch_only_on_unite_model() -> None:
    """The phase switch exists for the Unite model and not for the Next."""

    from custom_components.webasto_next_modbus.const import (
        MODEL_NEXT,
        MODEL_UNITE,
        get_switch_registers,
    )

    assert get_switch_registers(MODEL_NEXT) == ()
    assert any(register.key == "phase_switch" for register in get_switch_registers(MODEL_UNITE))


async def test_unite_number_of_phases_tracks_phase_switch_register() -> None:
    """The Unite phase-mode sensor reads the phase-switch register (405), not 404."""

    from custom_components.webasto_next_modbus.const import MODEL_UNITE, get_sensor_registers

    register = next(r for r in get_sensor_registers(MODEL_UNITE) if r.key == "number_of_phases")
    assert register.address == 405
    assert register.register_type == "holding"
