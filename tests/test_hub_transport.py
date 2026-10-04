"""Transport-level tests for the Modbus bridge (retries, close, life bit)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

import pytest
from modbus_connection import (
    AcknowledgeError,
    IllegalDataAddressError,
    IllegalFunctionError,
    ModbusConnectionError,
    ModbusTcpParams,
    ModbusTimeoutError,
    ServerDeviceBusyError,
)

from custom_components.webasto_next_modbus import hub as hub_module
from custom_components.webasto_next_modbus.const import RegisterDefinition, get_register
from custom_components.webasto_next_modbus.hub import (
    LIFE_BIT_DEFAULT_COM_TIMEOUT,
    LIFE_BIT_MAX_INTERVAL,
    LIFE_BIT_MIN_INTERVAL,
    READ_ATTEMPTS,
    REQUEST_TIMEOUT,
    WRITE_ATTEMPTS,
    ModbusBridge,
    WebastoModbusDeviceError,
    WebastoModbusError,
    life_bit_interval,
)

CORE = RegisterDefinition(
    key="charge_point_state",
    name="Charge point state",
    address=1000,
    count=1,
    register_type="holding",
    data_type="uint16",
    entity="sensor",
)
OPTIONAL = RegisterDefinition(
    key="smart_vehicle_detected",
    name="Smart vehicle",
    address=1620,
    count=2,
    register_type="holding",
    data_type="uint32",
    entity="sensor",
    optional=True,
)

Behaviour = Callable[[str, int, int], Awaitable[list[int] | None]]


class ScriptedUnit:
    """Fake ``ModbusUnit`` recording every request; behaviour set per test."""

    def __init__(self, behaviour: Behaviour | None = None) -> None:
        self.requests: list[tuple[str, int, int]] = []
        self.disconnects = 0
        self.timeout: float | None = None
        self.behaviour = behaviour

    def require_timeout(self, seconds: float | None) -> None:
        self.timeout = seconds

    async def _run(self, kind: str, address: int, count_or_value: int) -> list[int] | None:
        self.requests.append((kind, address, count_or_value))
        if self.behaviour is not None:
            return await self.behaviour(kind, address, count_or_value)
        return [1] * count_or_value if kind != "write" else None

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        result = await self._run("holding", address, count)
        assert result is not None
        return result

    async def read_input_registers(self, address: int, count: int) -> list[int]:
        result = await self._run("input", address, count)
        assert result is not None
        return result

    async def write_register(self, address: int, value: int) -> None:
        await self._run("write", address, value)

    async def disconnect(self) -> None:
        self.disconnects += 1


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hub_module, "RETRY_BACKOFF", 0)


def _bridge(unit: Any, *registers: RegisterDefinition) -> ModbusBridge:
    return ModbusBridge(unit, host="wallbox", port=502, unit_id=255, registers=registers or (CORE,))


def _raising(error: Exception) -> Behaviour:
    async def _behaviour(_kind: str, _address: int, _count: int) -> list[int] | None:
        raise error

    return _behaviour


async def test_bridge_asks_for_its_request_timeout() -> None:
    unit = ScriptedUnit()
    _bridge(unit)

    assert unit.timeout == REQUEST_TIMEOUT


async def test_bridge_works_without_require_timeout() -> None:
    """modbus-connection < 4.11 (HA 2026.9) has no ``require_timeout``."""

    class _OldUnit(ScriptedUnit):
        require_timeout = None  # type: ignore[assignment]

    bridge = _bridge(_OldUnit())

    assert await bridge.async_read_register(CORE) == 1


async def test_transport_errors_are_retried() -> None:
    unit = ScriptedUnit(_raising(ModbusConnectionError("connection refused")))
    bridge = _bridge(unit)

    with pytest.raises(WebastoModbusError, match="connection refused"):
        await bridge.async_read_register(CORE)

    assert len(unit.requests) == READ_ATTEMPTS


async def test_write_uses_fewer_attempts_than_read() -> None:
    unit = ScriptedUnit(_raising(ModbusConnectionError("connection lost")))
    bridge = _bridge(unit)

    with pytest.raises(WebastoModbusError):
        await bridge.async_write_register(get_register("set_current_a"), 10)

    assert len(unit.requests) == WRITE_ATTEMPTS


async def test_device_exception_is_not_retried() -> None:
    """The wallbox answered and refused: retrying won't change the answer."""

    unit = ScriptedUnit(_raising(IllegalDataAddressError(2)))
    bridge = _bridge(unit)

    with pytest.raises(WebastoModbusDeviceError, match="Illegal Data Address"):
        await bridge.async_read_register(CORE)

    assert len(unit.requests) == 1


async def test_timeout_drops_the_link() -> None:
    """A dead peer gets a fresh link on the next attempt instead of more waiting."""

    unit = ScriptedUnit(_raising(ModbusTimeoutError("no response")))
    bridge = _bridge(unit)

    with pytest.raises(WebastoModbusError, match="timed out"):
        await bridge.async_read_register(CORE)

    assert unit.disconnects == READ_ATTEMPTS


async def test_operation_has_a_total_time_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """A wallbox that never answers can't block a call for minutes."""

    monkeypatch.setattr(hub_module, "OPERATION_TIMEOUT", 0.2)

    async def _hang(_kind: str, _address: int, _count: int) -> list[int] | None:
        await asyncio.sleep(3600)
        return None

    unit = ScriptedUnit(_hang)
    bridge = _bridge(unit)

    async with asyncio.timeout(5):
        with pytest.raises(WebastoModbusError, match="timed out"):
            await bridge.async_read_register(CORE)
    # The request that was still waiting when the budget ran out never saw
    # its own timeout, so the budget drops the link itself.
    assert unit.disconnects == 1


async def test_cancellation_is_not_swallowed() -> None:
    async def _hang(_kind: str, _address: int, _count: int) -> list[int] | None:
        await asyncio.sleep(3600)
        return None

    unit = ScriptedUnit(_hang)
    bridge = _bridge(unit)

    task = asyncio.create_task(bridge.async_read_register(CORE))
    await asyncio.sleep(0.05)
    task.cancel()
    async with asyncio.timeout(2):
        with pytest.raises(asyncio.CancelledError):
            await task
    assert len(unit.requests) == 1


async def test_close_is_final_even_for_a_running_operation() -> None:
    """After close (the entry releases the shared connection) nothing is sent."""

    release = asyncio.Event()

    async def _slow_then_lost(_kind: str, _address: int, _count: int) -> list[int] | None:
        await release.wait()
        raise ModbusConnectionError("connection is closed")

    unit = ScriptedUnit(_slow_then_lost)
    bridge = _bridge(unit)
    task = asyncio.create_task(bridge.async_read_register(CORE))
    await asyncio.sleep(0.01)

    await bridge.async_close()
    release.set()

    with pytest.raises(WebastoModbusError):
        await task
    # The retry loop must not send another request after the close.
    assert len(unit.requests) == 1
    with pytest.raises(WebastoModbusError, match="closed"):
        await bridge.async_read_register(CORE)
    assert len(unit.requests) == 1


async def test_core_block_error_means_wallbox_not_responding() -> None:
    unit = ScriptedUnit(_raising(ServerDeviceBusyError(6)))
    bridge = _bridge(unit, CORE, OPTIONAL)

    with pytest.raises(WebastoModbusDeviceError, match="not responding"):
        await bridge.async_read_data()

    # The remaining blocks are skipped.
    assert unit.requests == [("holding", CORE.address, CORE.count)]


@pytest.mark.parametrize(
    ("error", "pruned"),
    [
        (IllegalFunctionError(1), True),
        (IllegalDataAddressError(2), True),
        (AcknowledgeError(5), False),
        (ServerDeviceBusyError(6), False),
    ],
)
async def test_optional_block_pruned_only_when_unsupported(error: Exception, pruned: bool) -> None:
    async def _optional_fails(_kind: str, address: int, count: int) -> list[int] | None:
        if address == OPTIONAL.address:
            raise error
        return [1] * count

    bridge = _bridge(ScriptedUnit(_optional_fails), CORE, OPTIONAL)

    data = await bridge.async_read_data()

    assert data[CORE.key] == 1
    assert data[OPTIONAL.key] is None
    remaining = [request.start_address for request in bridge._read_plan]
    assert (OPTIONAL.address in remaining) is not pruned


async def test_life_bit_write_happens_even_if_reads_fail() -> None:
    """A failed comTimeout read must not gate the keep-alive write."""

    async def _reads_fail(kind: str, address: int, _count: int) -> list[int] | None:
        if kind == "write":
            return None
        raise ModbusTimeoutError(f"read @{address} timed out")

    unit = ScriptedUnit(_reads_fail)
    interval = await _bridge(unit)._async_life_bit_cycle()

    assert [request for request in unit.requests if request[0] == "write"] == [("write", 6000, 1)]
    assert interval == LIFE_BIT_DEFAULT_COM_TIMEOUT / 2


@pytest.mark.parametrize(
    ("com_timeout", "expected"),
    [
        (60, 30.0),
        (20, 10.0),
        (6, 3.0),
        (2, LIFE_BIT_MIN_INTERVAL),
        (600, LIFE_BIT_MAX_INTERVAL),
        (0, LIFE_BIT_DEFAULT_COM_TIMEOUT / 2),
        (None, LIFE_BIT_DEFAULT_COM_TIMEOUT / 2),
        ("garbage", LIFE_BIT_DEFAULT_COM_TIMEOUT / 2),
    ],
)
def test_life_bit_interval_is_half_the_com_timeout(com_timeout: object, expected: float) -> None:
    assert life_bit_interval(com_timeout) == expected


async def test_life_bit_cycle_writes_one_and_returns_interval() -> None:
    async def _wallbox(kind: str, address: int, count: int) -> list[int] | None:
        if kind == "write":
            return None
        return {2002: [20]}.get(address, [1] * count)

    unit = ScriptedUnit(_wallbox)
    interval = await _bridge(unit)._async_life_bit_cycle()

    # Only comTimeout is read. The life bit itself is not read back: the
    # wallbox clears it about comTimeout/2 after the write, so right before
    # the next write it still holds our 1.
    assert unit.requests == [("holding", 2002, 1), ("write", 6000, 1)]
    assert interval == 10.0


async def test_life_bit_backoff_ends_when_wallbox_reachable() -> None:
    bridge = _bridge(ScriptedUnit())

    waiter = asyncio.create_task(bridge._async_wait_reachable(3600))
    await asyncio.sleep(0)
    bridge.notify_reachable()

    async with asyncio.timeout(1):
        await waiter


# --------------------------------------------------------------------------- #
# Real modbus-connection (tmodbus) against a server that never answers
# --------------------------------------------------------------------------- #


@pytest.fixture
async def silent_server() -> AsyncGenerator[tuple[int, list[asyncio.StreamWriter]]]:
    connections: list[asyncio.StreamWriter] = []

    async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        connections.append(writer)
        try:
            while await reader.read(1024):
                pass  # swallow requests, never reply
        finally:
            writer.close()

    server = await asyncio.start_server(_handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    yield port, connections
    server.close()
    for writer in connections:
        writer.close()
    await server.wait_closed()


@pytest.mark.enable_socket
async def test_real_connection_recovers_from_a_silent_peer(
    socket_enabled: None,
    silent_server: tuple[int, list[asyncio.StreamWriter]],
) -> None:
    """Timed-out requests drop their link, so no half-dead socket is kept open."""

    from modbus_connection.tmodbus import ModbusConnection

    port, connections = silent_server
    connection = ModbusConnection(ModbusTcpParams(host="127.0.0.1", port=port), timeout=0.2)
    bridge = ModbusBridge(
        connection.for_unit(255), host="127.0.0.1", port=port, unit_id=255, registers=(CORE,)
    )

    with pytest.raises(WebastoModbusError, match="timed out"):
        await bridge.async_read_register(CORE)
    await asyncio.sleep(0.1)

    # Each attempt used its own link, and every timed-out one was dropped.
    assert len(connections) == READ_ATTEMPTS
    assert [writer for writer in connections if not writer.is_closing()] == []
    await connection.close()
