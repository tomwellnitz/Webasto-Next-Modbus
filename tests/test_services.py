"""Service handler and runtime resolution tests for the Webasto Next Modbus integration."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant, ServiceCall

from custom_components.webasto_next_modbus import (
    DOMAIN,
    KEEPALIVE_TRIGGER_VALUE,
    RuntimeData,
    _async_service_send_keepalive,
    _async_service_set_current,
    _async_service_set_failsafe,
    _resolve_runtime,
)
from custom_components.webasto_next_modbus.const import get_register
from custom_components.webasto_next_modbus.coordinator import WebastoDataCoordinator
from custom_components.webasto_next_modbus.hub import ModbusBridge


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


def _make_runtime() -> RuntimeData:
    bridge = cast(ModbusBridge, SimpleNamespace())
    bridge.async_write_register = AsyncMock()  # type: ignore[attr-defined]
    coordinator = cast(WebastoDataCoordinator, SimpleNamespace())
    coordinator.async_request_refresh = AsyncMock()  # type: ignore[attr-defined]
    return RuntimeData(bridge=bridge, coordinator=coordinator)


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
async def test_service_set_current_clamps_and_refreshes() -> None:
    """Current service should clamp value and trigger coordinator refresh."""

    runtime = _make_runtime()
    hass = _make_hass({"entry": runtime})
    call = _make_call({"amps": 40}, hass=hass)

    register = get_register("set_current_a")

    await _async_service_set_current(call)

    runtime.bridge.async_write_register.assert_awaited_once_with(  # type: ignore[attr-defined]
        register,
        register.max_value,
    )
    runtime.coordinator.async_request_refresh.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_service_set_failsafe_writes_optional_timeout() -> None:
    """Failsafe service should write both registers when timeout provided."""

    runtime = _make_runtime()
    hass = _make_hass({"entry": runtime})
    call = _make_call({"amps": 100, "timeout_s": 200}, hass=hass)

    current_register = get_register("failsafe_current_a")
    timeout_register = get_register("failsafe_timeout_s")

    await _async_service_set_failsafe(call)

    runtime.bridge.async_write_register.assert_any_await(  # type: ignore[attr-defined]
        current_register,
        current_register.max_value,
    )
    runtime.bridge.async_write_register.assert_any_await(  # type: ignore[attr-defined]
        timeout_register,
        timeout_register.max_value,
    )
    runtime.coordinator.async_request_refresh.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_service_send_keepalive_triggers_write_and_refresh() -> None:
    """Keepalive service writes the trigger value and refreshes coordinator."""

    runtime = _make_runtime()
    hass = _make_hass({"entry": runtime})
    call = _make_call({}, hass=hass)

    register = get_register("send_keepalive")

    await _async_service_send_keepalive(call)

    runtime.bridge.async_write_register.assert_awaited_once_with(  # type: ignore[attr-defined]
        register,
        KEEPALIVE_TRIGGER_VALUE,
    )
    runtime.coordinator.async_request_refresh.assert_awaited_once()  # type: ignore[attr-defined]