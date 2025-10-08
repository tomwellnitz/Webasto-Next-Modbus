"""Tests for device triggers in the Webasto Next Modbus integration."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.helpers.trigger import TriggerInfo

from custom_components.webasto_next_modbus import device_trigger
from custom_components.webasto_next_modbus.const import DOMAIN
from custom_components.webasto_next_modbus.device_trigger import (
    SIGNAL_DEVICE_TRIGGER,
    TRIGGER_CHARGING_STARTED,
    async_fire_device_trigger,
)

pytestmark = pytest.mark.asyncio


def _make_hass() -> MagicMock:
    loop = asyncio.get_running_loop()
    hass = MagicMock()
    hass.loop = loop
    hass.async_create_task = loop.create_task
    hass.data = {}
    return hass


async def test_async_get_triggers_returns_supported_types() -> None:
    """Ensure async_get_triggers exposes all supported trigger types."""

    hass = _make_hass()
    device_entry = SimpleNamespace(identifiers={(DOMAIN, "mock-device")})
    registry = MagicMock()
    registry.async_get.return_value = device_entry

    with patch(
        "custom_components.webasto_next_modbus.device_trigger.dr.async_get",
        return_value=registry,
    ):
        triggers = await device_trigger.async_get_triggers(hass, "device-id")

    assert len(triggers) == len(device_trigger.TRIGGER_TYPES)
    assert {trigger[CONF_TYPE] for trigger in triggers} == set(device_trigger.TRIGGER_TYPES)
    for trigger in triggers:
        assert trigger[CONF_PLATFORM] == "device"
        assert trigger[CONF_DOMAIN] == DOMAIN
        assert trigger[CONF_DEVICE_ID] == "device-id"


async def test_async_attach_trigger_invokes_action_on_dispatch() -> None:
    """Attaching a trigger should subscribe to dispatcher and execute the action."""

    hass = _make_hass()
    device_entry = SimpleNamespace(identifiers={(DOMAIN, "mock-device")})
    registry = MagicMock()
    registry.async_get.return_value = device_entry

    captured_signal: str | None = None
    dispatcher_callback = None

    def _fake_connect(_hass, signal, callback):
        nonlocal captured_signal, dispatcher_callback
        captured_signal = signal
        dispatcher_callback = callback
        return lambda: None

    action = AsyncMock()
    trigger_info = cast(TriggerInfo, SimpleNamespace(context=None))

    with (
        patch(
            "custom_components.webasto_next_modbus.device_trigger.dr.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.webasto_next_modbus.device_trigger.async_dispatcher_connect",
            side_effect=_fake_connect,
        ),
    ):
        await device_trigger.async_attach_trigger(
            hass,
            {
                CONF_PLATFORM: "device",
                CONF_DOMAIN: DOMAIN,
                CONF_DEVICE_ID: "device-id",
                CONF_TYPE: TRIGGER_CHARGING_STARTED,
            },
            action,
            trigger_info,
        )

    assert captured_signal == SIGNAL_DEVICE_TRIGGER.format(device_slug="mock-device")
    assert dispatcher_callback is not None

    dispatcher_callback(TRIGGER_CHARGING_STARTED, {"foo": "bar"})
    await asyncio.sleep(0)

    action.assert_awaited_once()
    await_args = action.await_args
    assert await_args is not None
    payload, context = await_args.args
    assert payload[CONF_TYPE] == TRIGGER_CHARGING_STARTED
    assert payload["foo"] == "bar"
    assert context is None


async def test_async_fire_device_trigger_emits_dispatch() -> None:
    """async_fire_device_trigger should send dispatcher events."""

    hass = _make_hass()
    dispatcher = MagicMock()

    with patch(
        "custom_components.webasto_next_modbus.device_trigger.async_dispatcher_send",
        dispatcher,
    ):
        async_fire_device_trigger(hass, "mock-device", TRIGGER_CHARGING_STARTED, {"foo": "bar"})

    dispatcher.assert_called_once_with(
        hass,
        SIGNAL_DEVICE_TRIGGER.format(device_slug="mock-device"),
        TRIGGER_CHARGING_STARTED,
        {"foo": "bar"},
    )
