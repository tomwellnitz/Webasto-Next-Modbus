"""Pytest fixtures for Webasto Next Modbus integration tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from syrupy.assertion import SnapshotAssertion

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


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Serialise Home Assistant objects (states, registry entries) stably.

    Two pytest plugins define ``snapshot``; pin the Home Assistant extension so
    timestamps, IDs and contexts never end up in the snapshots.
    """

    return snapshot.use_extension(HomeAssistantSnapshotExtension)


@pytest.fixture(autouse=True)
def _reset_virtual_wallbox_registry() -> Generator[None]:
    """Ensure each test starts with a clean virtual wallbox registry."""

    virtual_registry.clear()
    yield
    virtual_registry.clear()


@pytest.fixture
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


def make_config_entry(
    *,
    options: dict[str, Any] | None = None,
    model: str | None = None,
    entry_id: str | None = None,
) -> Any:
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
        entry_id=entry_id,
    )


@pytest.fixture
def config_entry() -> Any:
    return make_config_entry()
