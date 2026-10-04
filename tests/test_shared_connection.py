"""End to end: Home Assistant's shared Modbus connection against the TCP simulator.

No fakes between the integration and the wire: the entry gets its unit from
``homeassistant.components.modbus.async_get_unit`` (modbus-connection with the
tmodbus backend) and talks Modbus TCP to ``virtual_wallbox.serve_tcp``.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.components.modbus.connection import DATA_MODBUS_CONNECTIONS
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from modbus_connection import ModbusTcpParams
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
from virtual_wallbox import serve_tcp
from virtual_wallbox.simulator import VirtualWallboxState, build_default_scenario

pytestmark = [pytest.mark.usefixtures("enable_custom_integrations"), pytest.mark.enable_socket]

HOST = "127.0.0.1"
UNIT_ID = 255


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


@pytest.fixture
async def tcp_wallbox(socket_enabled: None) -> AsyncGenerator[tuple[VirtualWallboxState, int]]:
    """Run the virtual wallbox as a real Modbus TCP server."""

    state = build_default_scenario(unit_id=UNIT_ID).create_state()
    port = _free_port()
    # zero_mode: the wire address is the register number, which is how the
    # integration (and the vendor spec) address registers. The simulator's
    # default "1-based" mode shifts every read by one register.
    server = asyncio.create_task(serve_tcp(state, host=HOST, port=port, zero_mode=True))
    for _ in range(100):
        try:
            _reader, writer = await asyncio.open_connection(HOST, port)
        except OSError:
            await asyncio.sleep(0.02)
            continue
        writer.close()
        await writer.wait_closed()
        break
    else:  # pragma: no cover - environment problem
        pytest.fail("virtual wallbox TCP server did not start")
    yield state, port
    server.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await server


def _entry(port: int) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Wallbox",
        unique_id=f"{HOST}-{UNIT_ID}",
        version=1,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
        data={
            CONF_HOST: HOST,
            CONF_PORT: port,
            CONF_UNIT_ID: UNIT_ID,
            CONF_SCAN_INTERVAL: 10,
            CONF_VARIANT: VARIANT_22_KW,
            CONF_MODEL: MODEL_NEXT,
        },
    )


def _consumers(hass: HomeAssistant, port: int) -> int | None:
    connections: dict[Any, Any] = hass.data.get(DATA_MODBUS_CONNECTIONS, {})
    shared = connections.get(ModbusTcpParams(host=HOST, port=port).endpoint)
    return None if shared is None else int(shared.consumers)


async def test_entry_runs_on_the_shared_connection(
    hass: HomeAssistant, tcp_wallbox: tuple[VirtualWallboxState, int]
) -> None:
    """Setup, polling, a write, sharing with a probe, and release on unload."""

    state, port = tcp_wallbox
    state.apply_values({"active_power_total_w": 7400})
    entry = _entry(port)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    power = hass.states.get("sensor.wallbox_active_power_total")
    assert power is not None
    assert power.state == "7400"
    assert _consumers(hass, port) == 1

    # A write goes over the same connection.
    await hass.services.async_call(
        DOMAIN, "set_failsafe", {"amps": 10, "timeout_s": 30}, blocking=True
    )
    assert state.read_block("holding", 2000, 1) == [10]

    # A config-flow probe of the same wallbox shares the entry's connection
    # instead of opening a second one (the wallbox has a single Modbus slot).
    async with async_get_temporary_unit(hass, ModbusTcpParams(host=HOST, port=port), UNIT_ID):
        assert _consumers(hass, port) == 2
    assert _consumers(hass, port) == 1

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert _consumers(hass, port) is None
