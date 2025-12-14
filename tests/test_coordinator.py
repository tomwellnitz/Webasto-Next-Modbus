"""Tests for the Webasto data update coordinator."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.webasto_next_modbus.coordinator import WebastoDataCoordinator
from custom_components.webasto_next_modbus.device_trigger import (
    TRIGGER_CHARGING_STARTED,
    TRIGGER_CHARGING_STOPPED,
    TRIGGER_CONNECTION_LOST,
    TRIGGER_CONNECTION_RESTORED,
)
from custom_components.webasto_next_modbus.hub import ModbusBridge, WebastoModbusError

pytestmark = pytest.mark.asyncio


def _make_hass() -> MagicMock:
    loop = asyncio.get_running_loop()
    hass = MagicMock()
    hass.loop = loop
    hass.data = {}
    hass.bus = MagicMock()
    hass.bus.async_listen_once = MagicMock(return_value=None)
    hass.config_entries = MagicMock()
    hass.config_entries.async_on_unload = MagicMock()
    hass.async_run_hass_job = MagicMock(return_value=None)
    hass.async_create_task = loop.create_task
    hass.async_add_job = MagicMock()
    hass.async_create_background_task = MagicMock()
    return hass


def _build_coordinator(bridge: ModbusBridge, entry: MockConfigEntry) -> WebastoDataCoordinator:
    hass = _make_hass()
    with patch("homeassistant.helpers.update_coordinator.Debouncer") as debouncer_cls:
        debouncer = MagicMock()
        debouncer.async_shutdown = MagicMock()
        debouncer.async_cancel = MagicMock()
        debouncer_cls.return_value = debouncer
        return WebastoDataCoordinator(
            hass,
            "1234",
            bridge,
            timedelta(seconds=5),
            "192.0.2.1-255",
            config_entry=entry,
        )


async def test_coordinator_success_resets_failures() -> None:
    """Successful updates should reset failure counters and timestamps."""

    bridge = AsyncMock(spec=ModbusBridge)
    bridge.async_read_data = AsyncMock(return_value={"foo": 1})
    entry = MockConfigEntry(domain="webasto_next_modbus", entry_id="1234")

    coordinator = _build_coordinator(bridge, entry)

    with patch(
        "custom_components.webasto_next_modbus.coordinator.persistent_notification.async_dismiss"
    ) as dismiss:
        data = await coordinator._async_update_data()

    assert data == {"foo": 1}
    assert coordinator.consecutive_failures == 0
    assert coordinator.last_success is not None
    dismiss.assert_called_once()


async def test_coordinator_failure_increments_counter() -> None:
    """Failures should increment counters and raise UpdateFailed."""

    bridge = AsyncMock(spec=ModbusBridge)
    bridge.async_read_data = AsyncMock(side_effect=WebastoModbusError("boom"))
    entry = MockConfigEntry(domain="webasto_next_modbus", entry_id="1234")

    coordinator = _build_coordinator(bridge, entry)

    with patch(
        "custom_components.webasto_next_modbus.coordinator.persistent_notification.async_create"
    ) as create:
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    assert coordinator.consecutive_failures == 1
    assert coordinator.last_failure is not None
    assert coordinator.last_error == "boom"
    create.assert_not_called()


async def test_coordinator_failure_triggers_notification() -> None:
    """After threshold failures a persistent notification should be created."""

    bridge = AsyncMock(spec=ModbusBridge)
    bridge.async_read_data = AsyncMock(side_effect=WebastoModbusError("boom"))
    entry = MockConfigEntry(domain="webasto_next_modbus", entry_id="1234")

    coordinator = _build_coordinator(bridge, entry)
    coordinator.consecutive_failures = 2

    with patch(
        "custom_components.webasto_next_modbus.coordinator.persistent_notification.async_create"
    ) as create:
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    create.assert_called_once()


async def test_coordinator_emits_charging_started_trigger() -> None:
    """Starting to charge should fire the charging_started trigger."""

    bridge = AsyncMock(spec=ModbusBridge)
    bridge.async_read_data = AsyncMock(return_value={"charging_state": 1, "charge_point_state": 3})
    entry = MockConfigEntry(domain="webasto_next_modbus", entry_id="1234")

    coordinator = _build_coordinator(bridge, entry)
    coordinator.data = {"charging_state": 0}

    with patch(
        "custom_components.webasto_next_modbus.coordinator.async_fire_device_trigger"
    ) as fire:
        await coordinator._async_update_data()

    fire.assert_any_call(
        coordinator.hass,
        "192.0.2.1-255",
        TRIGGER_CHARGING_STARTED,
        {
            "charging_state": 1,
            "previous_state": 0,
            "charge_point_state": 3,
        },
    )


async def test_coordinator_emits_charging_stopped_trigger() -> None:
    """Stopping charging should fire the charging_stopped trigger."""

    bridge = AsyncMock(spec=ModbusBridge)
    bridge.async_read_data = AsyncMock(return_value={"charging_state": 0})
    entry = MockConfigEntry(domain="webasto_next_modbus", entry_id="1234")

    coordinator = _build_coordinator(bridge, entry)
    coordinator.data = {"charging_state": 1}

    with patch(
        "custom_components.webasto_next_modbus.coordinator.async_fire_device_trigger"
    ) as fire:
        await coordinator._async_update_data()

    fire.assert_any_call(
        coordinator.hass,
        "192.0.2.1-255",
        TRIGGER_CHARGING_STOPPED,
        {
            "charging_state": 0,
            "previous_state": 1,
            "charge_point_state": None,
        },
    )


async def test_coordinator_emits_connection_triggers() -> None:
    """Connection loss and recovery should emit corresponding triggers."""

    bridge = AsyncMock(spec=ModbusBridge)
    bridge.async_read_data = AsyncMock(
        side_effect=[WebastoModbusError("boom"), {"charging_state": 0}]
    )
    entry = MockConfigEntry(domain="webasto_next_modbus", entry_id="1234")

    coordinator = _build_coordinator(bridge, entry)

    with patch(
        "custom_components.webasto_next_modbus.coordinator.async_fire_device_trigger"
    ) as fire:
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
        await coordinator._async_update_data()

    lost_call = next(
        call for call in fire.call_args_list if call.args[2] == TRIGGER_CONNECTION_LOST
    )
    assert lost_call.args[1] == "192.0.2.1-255"
    assert lost_call.args[3] == {"error": "boom"}

    restored_call = next(
        call for call in fire.call_args_list if call.args[2] == TRIGGER_CONNECTION_RESTORED
    )
    assert restored_call.args[1] == "192.0.2.1-255"
    assert "timestamp" in restored_call.args[3]
