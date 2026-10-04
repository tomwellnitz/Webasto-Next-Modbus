"""Tests for Modbus bridge helpers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.webasto_next_modbus.const import (
    MODEL_UNITE,
    SESSION_COMMAND_RESET_DELAY,
    SESSION_COMMAND_START_VALUE,
    RegisterDefinition,
    get_readable_registers,
)
from custom_components.webasto_next_modbus.hub import (
    ModbusBridge,
    WebastoModbusDeviceError,
    WebastoModbusError,
    _build_read_plan,
    _describe_modbus_response,
)


def test_device_error_is_subclass_of_modbus_error() -> None:
    """Device exceptions must still be caught by handlers expecting WebastoModbusError."""

    assert issubclass(WebastoModbusDeviceError, WebastoModbusError)


def test_describe_modbus_response_with_known_code() -> None:
    text = _describe_modbus_response(SimpleNamespace(exception_code=2))
    assert "exception code 2" in text
    assert "Illegal Data Address" in text


def test_describe_modbus_response_with_unknown_code() -> None:
    text = _describe_modbus_response(SimpleNamespace(exception_code=99))
    assert "exception code 99" in text
    assert "unknown" in text


def test_describe_modbus_response_falls_back_to_str() -> None:
    # No exception_code attribute -> uses str() of the response.
    assert "boom" in _describe_modbus_response(SimpleNamespace(detail="boom"))


def test_read_plan_puts_optional_blocks_last() -> None:
    """The first block decides reachability, so it must not be optional."""

    plan = _build_read_plan(get_readable_registers(MODEL_UNITE))

    optional_flags = [all(reg.optional for reg in request.registers) for request in plan]
    assert any(optional_flags)
    assert not optional_flags[0]
    first_optional = optional_flags.index(True)
    assert all(optional_flags[first_optional:])


class _ErrorResult:
    exception_code = 2

    def isError(self) -> bool:
        return True


class _OkResult:
    def __init__(self, count: int) -> None:
        self.registers = [7] * count

    def isError(self) -> bool:
        return False


class _ClientWithoutRegister405:
    """Fake pymodbus client for a firmware that lacks holding register 405."""

    def __init__(self, host: str, **_kwargs: Any) -> None:
        self.connected = False

    async def connect(self) -> bool:
        self.connected = True
        return True

    def close(self) -> None:
        self.connected = False

    async def read_holding_registers(self, address: int, count: int, **_kwargs: Any) -> Any:
        if address == 405:
            return _ErrorResult()
        return _OkResult(count)

    async def read_input_registers(self, address: int, count: int, **_kwargs: Any) -> Any:
        return _OkResult(count)


async def test_unsupported_optional_register_does_not_block_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An optional block read first must not make the wallbox look offline."""

    from custom_components.webasto_next_modbus import hub as hub_module

    monkeypatch.setattr(
        hub_module, "_ensure_pymodbus", lambda: (_ClientWithoutRegister405, Exception)
    )
    optional = RegisterDefinition(
        key="number_of_phases",
        name="Number of phases",
        address=405,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="sensor",
        optional=True,
    )
    core = RegisterDefinition(
        key="charge_point_state",
        name="Charge point state",
        address=1000,
        count=1,
        register_type="input",
        data_type="uint16",
        entity="sensor",
    )
    bridge = ModbusBridge("wallbox", 502, 255, registers=(optional, core))

    data = await bridge.async_read_data()

    assert data["charge_point_state"] == 7
    assert data["number_of_phases"] is None
    # The unsupported block is dropped from the plan after the first failure.
    assert [request.start_address for request in bridge._read_plan] == [1000]
    await bridge.async_close()


async def test_session_command_resets_register_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """5006 only acts on a change, so the idle value is written before the command."""

    from custom_components.webasto_next_modbus import hub as hub_module

    monkeypatch.setattr(
        hub_module, "_ensure_pymodbus", lambda: (_ClientWithoutRegister405, Exception)
    )
    sleeps: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(hub_module.asyncio, "sleep", _fake_sleep)
    bridge = ModbusBridge("wallbox", 502, 255)
    written: list[tuple[str, int]] = []

    async def _record(register: RegisterDefinition, value: int) -> None:
        written.append((register.key, value))

    monkeypatch.setattr(bridge, "async_write_register", _record)

    await bridge.async_send_session_command(SESSION_COMMAND_START_VALUE)

    assert written == [("session_command", 0), ("session_command", SESSION_COMMAND_START_VALUE)]
    assert sleeps == [SESSION_COMMAND_RESET_DELAY]
