"""Tests for Modbus bridge helpers."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.webasto_next_modbus.hub import (
    WebastoModbusDeviceError,
    WebastoModbusError,
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
