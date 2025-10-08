"""Service handler and runtime resolution tests for the Webasto Next Modbus integration."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from custom_components.webasto_next_modbus import (
    DOMAIN,
    KEEPALIVE_TRIGGER_VALUE,
    TRIGGER_KEEPALIVE_SENT,
    RuntimeData,
    _async_service_send_keepalive,
    _async_service_set_current,
    _async_service_set_failsafe,
    _async_service_start_session,
    _async_service_stop_session,
    _resolve_runtime,
)
from custom_components.webasto_next_modbus.const import (
    SESSION_COMMAND_START_VALUE,
    SESSION_COMMAND_STOP_VALUE,
    SIGNAL_REGISTER_WRITTEN,
    VARIANT_11_KW,
    VARIANT_22_KW,
    build_device_slug,
    get_max_current_for_variant,
    get_register,
)
from custom_components.webasto_next_modbus.coordinator import WebastoDataCoordinator
from custom_components.webasto_next_modbus.hub import ModbusBridge, WebastoModbusError


def _make_hass(runtime_map: dict[str, RuntimeData] | None) -> HomeAssistant:
    hass = cast(HomeAssistant, SimpleNamespace(data={}))
    if runtime_map is not None:
        hass.data[DOMAIN] = dict(runtime_map)
    return hass


def _make_call(data: dict[str, Any], hass: HomeAssistant | None = None) -> ServiceCall:
    call = cast(ServiceCall, SimpleNamespace(data=data))
    if hass is not None:
        call.hass = hass  # type: ignore[attr-defined]
    return call


def _make_runtime(variant: str = VARIANT_22_KW) -> RuntimeData:
    bridge = cast(ModbusBridge, SimpleNamespace())
    bridge.async_write_register = AsyncMock()  # type: ignore[attr-defined]
    coordinator = cast(WebastoDataCoordinator, SimpleNamespace())
    coordinator.async_request_refresh = AsyncMock()  # type: ignore[attr-defined]
    return RuntimeData(
        bridge=bridge,
        coordinator=coordinator,
        variant=variant,
        max_current=get_max_current_for_variant(variant),
        device_slug=build_device_slug("192.0.2.1", 255),
        device_name="Test Wallbox",
    )


@pytest.fixture
def dispatcher_stub():
    with patch("custom_components.webasto_next_modbus.async_dispatcher_send") as mock_dispatch:
        yield mock_dispatch


def test_resolve_runtime_single_entry() -> None:
    """Single configured wallbox should resolve without config_entry_id."""

    runtime = _make_runtime()
    hass = _make_hass({"entry": runtime})
    call = _make_call({})

    result = _resolve_runtime(hass, call)

    assert result is runtime


def test_resolve_runtime_requires_entry_id() -> None:
    """When multiple wallboxes exist, config_entry_id must be provided."""

    runtime_a = _make_runtime()
    runtime_b = _make_runtime()
    hass = _make_hass({"entry_a": runtime_a, "entry_b": runtime_b})

    call_missing = _make_call({})
    with pytest.raises(ValueError):
        _resolve_runtime(hass, call_missing)

    call = _make_call({"config_entry_id": "entry_b"})
    assert _resolve_runtime(hass, call) is runtime_b


def test_resolve_runtime_missing_runtime_data() -> None:
    """Raise an error if runtime data has not been stored yet."""

    hass = _make_hass({"entry": cast(RuntimeData, SimpleNamespace())})
    call = _make_call({})

    with pytest.raises(ValueError):
        _resolve_runtime(hass, call)


@pytest.mark.asyncio
async def test_service_set_current_clamps_and_refreshes(dispatcher_stub) -> None:
    """Current service should clamp value and trigger coordinator refresh."""

    runtime = _make_runtime()
    hass = _make_hass({"entry": runtime})
    call = _make_call({"amps": 40}, hass=hass)

    register = get_register("set_current_a")

    await _async_service_set_current(call)

    runtime.bridge.async_write_register.assert_awaited_once_with(  # type: ignore[attr-defined]
        register,
        runtime.max_current,
    )
    runtime.coordinator.async_request_refresh.assert_awaited_once()  # type: ignore[attr-defined]
    dispatcher_stub.assert_called_once_with(
        call.hass,
        SIGNAL_REGISTER_WRITTEN,
        runtime.device_slug,
        register.key,
        runtime.max_current,
    )


@pytest.mark.asyncio
async def test_service_set_failsafe_writes_optional_timeout(dispatcher_stub) -> None:
    """Failsafe service should write both registers when timeout provided."""

    runtime = _make_runtime()
    hass = _make_hass({"entry": runtime})
    call = _make_call({"amps": 100, "timeout_s": 200}, hass=hass)

    current_register = get_register("failsafe_current_a")
    timeout_register = get_register("failsafe_timeout_s")

    await _async_service_set_failsafe(call)

    runtime.bridge.async_write_register.assert_any_await(  # type: ignore[attr-defined]
        current_register,
        runtime.max_current,
    )
    runtime.bridge.async_write_register.assert_any_await(  # type: ignore[attr-defined]
        timeout_register,
        timeout_register.max_value,
    )
    runtime.coordinator.async_request_refresh.assert_awaited_once()  # type: ignore[attr-defined]
    assert dispatcher_stub.call_count == 2
    dispatcher_stub.assert_any_call(
        call.hass,
        SIGNAL_REGISTER_WRITTEN,
        runtime.device_slug,
        current_register.key,
        runtime.max_current,
    )
    dispatcher_stub.assert_any_call(
        call.hass,
        SIGNAL_REGISTER_WRITTEN,
        runtime.device_slug,
        timeout_register.key,
        timeout_register.max_value,
    )


@pytest.mark.asyncio
async def test_service_variant_limits_current(dispatcher_stub) -> None:
    """Clamp current service to the variant limit when below register max."""

    runtime = _make_runtime(variant=VARIANT_11_KW)
    hass = _make_hass({"entry": runtime})
    call = _make_call({"amps": 40}, hass=hass)

    register = get_register("set_current_a")

    await _async_service_set_current(call)

    runtime.bridge.async_write_register.assert_awaited_once_with(  # type: ignore[attr-defined]
        register,
        runtime.max_current,
    )
    runtime.coordinator.async_request_refresh.assert_awaited_once()  # type: ignore[attr-defined]
    dispatcher_stub.assert_called_once_with(
        call.hass,
        SIGNAL_REGISTER_WRITTEN,
        runtime.device_slug,
        register.key,
        runtime.max_current,
    )


@pytest.mark.asyncio
async def test_service_variant_limits_failsafe(dispatcher_stub) -> None:
    """Clamp failsafe current to the variant limit."""

    runtime = _make_runtime(variant=VARIANT_11_KW)
    hass = _make_hass({"entry": runtime})
    call = _make_call({"amps": 40}, hass=hass)

    current_register = get_register("failsafe_current_a")

    await _async_service_set_failsafe(call)

    runtime.bridge.async_write_register.assert_any_await(  # type: ignore[attr-defined]
        current_register,
        runtime.max_current,
    )
    runtime.coordinator.async_request_refresh.assert_awaited_once()  # type: ignore[attr-defined]
    dispatcher_stub.assert_called_once_with(
        call.hass,
        SIGNAL_REGISTER_WRITTEN,
        runtime.device_slug,
        current_register.key,
        runtime.max_current,
    )


@pytest.mark.asyncio
async def test_service_send_keepalive_triggers_write_and_refresh(dispatcher_stub) -> None:
    """Keepalive service writes the trigger value and refreshes coordinator."""

    runtime = _make_runtime()
    hass = _make_hass({"entry": runtime})
    call = _make_call({}, hass=hass)

    register = get_register("send_keepalive")

    with patch("custom_components.webasto_next_modbus.async_fire_device_trigger") as mock_fire:
        await _async_service_send_keepalive(call)

    runtime.bridge.async_write_register.assert_awaited_once_with(  # type: ignore[attr-defined]
        register,
        KEEPALIVE_TRIGGER_VALUE,
    )
    runtime.coordinator.async_request_refresh.assert_awaited_once()  # type: ignore[attr-defined]
    mock_fire.assert_called_once_with(
        call.hass,
        runtime.device_slug,
        TRIGGER_KEEPALIVE_SENT,
        {"source": "service"},
    )
    dispatcher_stub.assert_not_called()


@pytest.mark.asyncio
async def test_service_start_session_writes_command(dispatcher_stub) -> None:
    """Start session service should write the start command."""

    runtime = _make_runtime()
    hass = _make_hass({"entry": runtime})
    call = _make_call({}, hass=hass)

    register = get_register("session_command")

    await _async_service_start_session(call)

    runtime.bridge.async_write_register.assert_awaited_once_with(  # type: ignore[attr-defined]
        register,
        SESSION_COMMAND_START_VALUE,
    )
    runtime.coordinator.async_request_refresh.assert_awaited_once()  # type: ignore[attr-defined]
    dispatcher_stub.assert_not_called()


@pytest.mark.asyncio
async def test_service_stop_session_writes_command(dispatcher_stub) -> None:
    """Stop session service should write the stop command."""

    runtime = _make_runtime()
    hass = _make_hass({"entry": runtime})
    call = _make_call({}, hass=hass)

    register = get_register("session_command")

    await _async_service_stop_session(call)

    runtime.bridge.async_write_register.assert_awaited_once_with(  # type: ignore[attr-defined]
        register,
        SESSION_COMMAND_STOP_VALUE,
    )
    runtime.coordinator.async_request_refresh.assert_awaited_once()  # type: ignore[attr-defined]
    dispatcher_stub.assert_not_called()


@pytest.mark.asyncio
async def test_session_services_surface_errors(dispatcher_stub) -> None:
    """Modbus errors should bubble up as HomeAssistantError."""

    runtime = _make_runtime()
    runtime.bridge.async_write_register.side_effect = WebastoModbusError("boom")  # type: ignore[attr-defined]
    hass = _make_hass({"entry": runtime})
    call = _make_call({}, hass=hass)

    with pytest.raises(HomeAssistantError):
        await _async_service_start_session(call)
    dispatcher_stub.assert_not_called()


@pytest.mark.asyncio
async def test_service_write_errors_surface_as_homeassistant_error(dispatcher_stub) -> None:
    """A Modbus write failure should surface as a HomeAssistantError."""

    runtime = _make_runtime()
    runtime.bridge.async_write_register.side_effect = WebastoModbusError("boom")  # type: ignore[attr-defined]
    hass = _make_hass({"entry": runtime})
    call = _make_call({"amps": 10}, hass=hass)

    with pytest.raises(HomeAssistantError):
        await _async_service_set_current(call)
    dispatcher_stub.assert_not_called()
