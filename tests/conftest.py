"""Pytest fixtures for Webasto Next Modbus integration tests."""

from __future__ import annotations

import sys
import types
from collections.abc import Generator
from typing import Any, cast

import pytest

from virtual_wallbox.simulator import (
    FakeAsyncModbusTcpClient,
    FakeModbusException,
    VirtualWallboxState,
    build_default_scenario,
    register_virtual_wallbox,
)
from virtual_wallbox.simulator import (
    registry as virtual_registry,
)

_pymodbus_client = types.ModuleType("pymodbus.client")
cast(Any, _pymodbus_client).AsyncModbusTcpClient = FakeAsyncModbusTcpClient

_pymodbus_exceptions = types.ModuleType("pymodbus.exceptions")
cast(Any, _pymodbus_exceptions).ModbusException = FakeModbusException

_pymodbus = types.ModuleType("pymodbus")
cast(Any, _pymodbus).client = _pymodbus_client
cast(Any, _pymodbus).exceptions = _pymodbus_exceptions

sys.modules.setdefault("pymodbus", _pymodbus)
sys.modules.setdefault("pymodbus.client", _pymodbus_client)
sys.modules.setdefault("pymodbus.exceptions", _pymodbus_exceptions)


_voluptuous = types.ModuleType("voluptuous")


class _DummyValidator:
    def __call__(self, value):
        return value


def _pass_through(*args, **kwargs):
    def _inner(value):
        return value

    return _inner


cast(Any, _voluptuous).Schema = lambda schema: _DummyValidator()
cast(Any, _voluptuous).Required = lambda *args, **kwargs: args[0] if args else None
cast(Any, _voluptuous).Optional = lambda *args, **kwargs: args[0] if args else None
cast(Any, _voluptuous).All = lambda *args, **kwargs: _DummyValidator()
cast(Any, _voluptuous).Range = _pass_through

sys.modules.setdefault("voluptuous", _voluptuous)


@pytest.fixture(autouse=True)
def _reset_virtual_wallbox_registry() -> Generator[None, None, None]:
    """Ensure each test starts with a clean virtual wallbox registry."""

    virtual_registry.clear()
    yield
    virtual_registry.clear()


@pytest.fixture()
def default_virtual_wallbox() -> Generator[VirtualWallboxState, None, None]:
    """Provide a default virtual wallbox matching ModbusBridge defaults."""

    with register_virtual_wallbox(
        host="127.0.0.1",
        port=15020,
        scenario=build_default_scenario(),
    ) as state:
        yield state
