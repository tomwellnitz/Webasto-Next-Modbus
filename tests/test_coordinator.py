"""Tests for the Webasto data update coordinator."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.webasto_next_modbus.const import CONF_REST_ENABLED, CONF_REST_PASSWORD
from custom_components.webasto_next_modbus.coordinator import WebastoDataCoordinator
from custom_components.webasto_next_modbus.device_trigger import (
    TRIGGER_CABLE_CONNECTED,
    TRIGGER_CABLE_DISCONNECTED,
    TRIGGER_CHARGING_STARTED,
    TRIGGER_CHARGING_STOPPED,
    TRIGGER_CONNECTION_LOST,
    TRIGGER_CONNECTION_RESTORED,
    TRIGGER_FAULT_OCCURRED,
)
from custom_components.webasto_next_modbus.hub import ModbusBridge, WebastoModbusError
from custom_components.webasto_next_modbus.rest_client import AuthenticationError

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


async def test_coordinator_emits_cable_connected_trigger() -> None:
    """Plugging a cable should fire the cable_connected trigger."""

    bridge = AsyncMock(spec=ModbusBridge)
    bridge.async_read_data = AsyncMock(return_value={"cable_state": 2})
    entry = MockConfigEntry(domain="webasto_next_modbus", entry_id="1234")

    coordinator = _build_coordinator(bridge, entry)
    coordinator.data = {"cable_state": 0}

    with patch(
        "custom_components.webasto_next_modbus.coordinator.async_fire_device_trigger"
    ) as fire:
        await coordinator._async_update_data()

    fire.assert_any_call(
        coordinator.hass,
        "192.0.2.1-255",
        TRIGGER_CABLE_CONNECTED,
        {"cable_state": 2, "previous_state": 0},
    )


async def test_coordinator_emits_cable_disconnected_trigger() -> None:
    """Unplugging the cable should fire the cable_disconnected trigger."""

    bridge = AsyncMock(spec=ModbusBridge)
    bridge.async_read_data = AsyncMock(return_value={"cable_state": 0})
    entry = MockConfigEntry(domain="webasto_next_modbus", entry_id="1234")

    coordinator = _build_coordinator(bridge, entry)
    coordinator.data = {"cable_state": 2}

    with patch(
        "custom_components.webasto_next_modbus.coordinator.async_fire_device_trigger"
    ) as fire:
        await coordinator._async_update_data()

    fire.assert_any_call(
        coordinator.hass,
        "192.0.2.1-255",
        TRIGGER_CABLE_DISCONNECTED,
        {"cable_state": 0, "previous_state": 2},
    )


async def test_coordinator_emits_fault_trigger() -> None:
    """A fault code appearing should fire the fault_occurred trigger once."""

    bridge = AsyncMock(spec=ModbusBridge)
    bridge.async_read_data = AsyncMock(return_value={"fault_code": 5})
    entry = MockConfigEntry(domain="webasto_next_modbus", entry_id="1234")

    coordinator = _build_coordinator(bridge, entry)
    coordinator.data = {"fault_code": 0}

    with patch(
        "custom_components.webasto_next_modbus.coordinator.async_fire_device_trigger"
    ) as fire:
        await coordinator._async_update_data()

    fire.assert_any_call(
        coordinator.hass,
        "192.0.2.1-255",
        TRIGGER_FAULT_OCCURRED,
        {"fault_code": 5},
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


async def test_coordinator_retries_rest_setup_when_due() -> None:
    """A previously failed REST setup is retried from the data poll once the interval passes."""

    bridge = AsyncMock(spec=ModbusBridge)
    bridge.async_read_data = AsyncMock(return_value={})
    entry = MockConfigEntry(domain="webasto_next_modbus", entry_id="1234")

    coordinator = _build_coordinator(bridge, entry)
    coordinator.async_setup_rest_client = AsyncMock()
    coordinator._rest_setup_retry_at = datetime.now(UTC) - timedelta(seconds=1)

    with patch(
        "custom_components.webasto_next_modbus.coordinator.persistent_notification.async_dismiss"
    ):
        await coordinator._async_update_data()

    coordinator.async_setup_rest_client.assert_awaited_once()


async def test_coordinator_does_not_retry_rest_setup_before_due() -> None:
    """The REST setup retry is throttled by `_rest_setup_retry_at`."""

    bridge = AsyncMock(spec=ModbusBridge)
    bridge.async_read_data = AsyncMock(return_value={})
    entry = MockConfigEntry(domain="webasto_next_modbus", entry_id="1234")

    coordinator = _build_coordinator(bridge, entry)
    coordinator.async_setup_rest_client = AsyncMock()
    coordinator._rest_setup_retry_at = datetime.now(UTC) + timedelta(minutes=10)

    with patch(
        "custom_components.webasto_next_modbus.coordinator.persistent_notification.async_dismiss"
    ):
        await coordinator._async_update_data()

    coordinator.async_setup_rest_client.assert_not_awaited()


async def test_coordinator_force_refreshes_rest_data() -> None:
    """`async_refresh_rest_data` bypasses the polling throttle and notifies listeners."""

    bridge = AsyncMock(spec=ModbusBridge)
    entry = MockConfigEntry(domain="webasto_next_modbus", entry_id="1234")
    coordinator = _build_coordinator(bridge, entry)

    sentinel = object()
    rest_client = MagicMock()
    rest_client.get_data = AsyncMock(return_value=sentinel)
    coordinator._rest_client = rest_client
    # A regular poll would skip the fetch because the interval hasn't elapsed.
    coordinator._rest_last_update = datetime.now(UTC)

    await coordinator.async_refresh_rest_data()

    rest_client.get_data.assert_awaited_once()
    assert coordinator.rest_data is sentinel


async def test_coordinator_rest_auth_failure_starts_reauth() -> None:
    """A 401 on the REST login starts a reauth flow and disables REST (no retry)."""

    bridge = AsyncMock(spec=ModbusBridge)
    bridge.endpoint = "192.0.2.1:502 (device_id 255)"
    entry = MockConfigEntry(
        domain="webasto_next_modbus",
        entry_id="1234",
        options={CONF_REST_ENABLED: True, CONF_REST_PASSWORD: "secret"},
    )
    coordinator = _build_coordinator(bridge, entry)

    with (
        patch.object(entry, "async_start_reauth") as start_reauth,
        patch("custom_components.webasto_next_modbus.coordinator.async_get_clientsession"),
        patch("custom_components.webasto_next_modbus.rest_client.RestClient") as mock_rc,
    ):
        mock_rc.return_value.connect = AsyncMock(side_effect=AuthenticationError("bad creds"))
        mock_rc.return_value.disconnect = AsyncMock()
        await coordinator.async_setup_rest_client()

    assert coordinator._rest_client is None
    assert coordinator._rest_setup_retry_at is None
    mock_rc.return_value.disconnect.assert_awaited_once()
    start_reauth.assert_called_once()


async def test_coordinator_rest_success_does_not_start_reauth() -> None:
    """A successful REST connect does not trigger a reauth flow."""

    bridge = AsyncMock(spec=ModbusBridge)
    bridge.endpoint = "192.0.2.1:502 (device_id 255)"
    entry = MockConfigEntry(
        domain="webasto_next_modbus",
        entry_id="1234",
        options={CONF_REST_ENABLED: True, CONF_REST_PASSWORD: "secret"},
    )
    coordinator = _build_coordinator(bridge, entry)

    with (
        patch.object(entry, "async_start_reauth") as start_reauth,
        patch("custom_components.webasto_next_modbus.coordinator.async_get_clientsession"),
        patch("custom_components.webasto_next_modbus.rest_client.RestClient") as mock_rc,
    ):
        mock_rc.return_value.connect = AsyncMock()
        mock_rc.return_value.disconnect = AsyncMock()
        await coordinator.async_setup_rest_client()

    assert coordinator._rest_client is mock_rc.return_value
    start_reauth.assert_not_called()
