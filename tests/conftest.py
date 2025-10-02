"""Pytest fixtures for Webasto Next Modbus integration tests."""

from __future__ import annotations

import sys
import types
from typing import Any, cast
from unittest.mock import MagicMock

_pymodbus_client = types.ModuleType("pymodbus.client")
cast(Any, _pymodbus_client).AsyncModbusTcpClient = MagicMock()

_pymodbus_exceptions = types.ModuleType("pymodbus.exceptions")


class _DummyModbusException(Exception):
	"""Fallback Modbus exception used within tests."""


cast(Any, _pymodbus_exceptions).ModbusException = _DummyModbusException

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
