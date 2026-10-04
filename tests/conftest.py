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
def _reset_virtual_wallbox_registry() -> Generator[None]:
    """Ensure each test starts with a clean virtual wallbox registry."""

    virtual_registry.clear()
    yield
    virtual_registry.clear()


@pytest.fixture()
def default_virtual_wallbox() -> Generator[VirtualWallboxState]:
    """Provide a default virtual wallbox matching ModbusBridge defaults."""

    with register_virtual_wallbox(
        host="127.0.0.1",
        port=15020,
        scenario=build_default_scenario(),
    ) as state:
        yield state


# --------------------------------------------------------------------------- #
# Fixtures for tests that run the integration inside a real Home Assistant.
# Modules opt in with
#   pytestmark = pytest.mark.usefixtures("enable_custom_integrations", "fake_pymodbus")
# --------------------------------------------------------------------------- #

HA_HOST = "192.0.2.10"
HA_PORT = 502
HA_UNIT_ID = 255


@pytest.fixture
def fake_pymodbus() -> Generator[None]:
    """Route the bridge's Modbus client to the virtual wallbox."""

    from unittest.mock import patch

    from custom_components.webasto_next_modbus import hub as hub_module

    with patch.object(
        hub_module,
        "_ensure_pymodbus",
        return_value=(FakeAsyncModbusTcpClient, FakeModbusException),
    ):
        yield


@pytest.fixture
def wallbox() -> Generator[VirtualWallboxState]:
    """Provide a virtual Webasto Next at HA_HOST:HA_PORT."""

    with register_virtual_wallbox(
        host=HA_HOST, port=HA_PORT, scenario=build_default_scenario(unit_id=HA_UNIT_ID)
    ) as state:
        yield state


def make_config_entry(*, options: dict[str, Any] | None = None, model: str | None = None) -> Any:
    """Return a MockConfigEntry for the virtual wallbox."""

    from homeassistant.const import CONF_HOST, CONF_PORT
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.webasto_next_modbus import CONFIG_ENTRY_MINOR_VERSION
    from custom_components.webasto_next_modbus.const import (
        CONF_MODEL,
        CONF_SCAN_INTERVAL,
        CONF_UNIT_ID,
        CONF_VARIANT,
        DOMAIN,
        MODEL_NEXT,
        VARIANT_22_KW,
    )

    return MockConfigEntry(
        domain=DOMAIN,
        title="Wallbox",
        unique_id=f"{HA_HOST}-{HA_UNIT_ID}",
        version=1,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
        data={
            CONF_HOST: HA_HOST,
            CONF_PORT: HA_PORT,
            CONF_UNIT_ID: HA_UNIT_ID,
            CONF_SCAN_INTERVAL: 10,
            CONF_VARIANT: VARIANT_22_KW,
            CONF_MODEL: model or MODEL_NEXT,
        },
        options=options or {},
    )


@pytest.fixture
def config_entry() -> Any:
    return make_config_entry()
