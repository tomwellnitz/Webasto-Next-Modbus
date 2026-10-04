"""Transport-level tests for the Modbus bridge (connections, retries, life bit)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest

from custom_components.webasto_next_modbus import hub as hub_module
from custom_components.webasto_next_modbus.const import RegisterDefinition, get_register
from custom_components.webasto_next_modbus.hub import (
    LIFE_BIT_DEFAULT_COM_TIMEOUT,
    LIFE_BIT_MAX_INTERVAL,
    LIFE_BIT_MIN_INTERVAL,
    READ_ATTEMPTS,
    WRITE_ATTEMPTS,
    ModbusBridge,
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


class FakeModbusError(Exception):
    """Stands in for pymodbus.exceptions.ModbusException."""


class _Ok:
    def __init__(self, count: int = 1) -> None:
        self.registers = [1] * count

    def isError(self) -> bool:
        return False


class _Err:
    def __init__(self, code: int) -> None:
        self.exception_code = code

    def isError(self) -> bool:
        return True


class ScriptedClient:
    """Fake pymodbus client recording its lifecycle; behaviour set per test."""

    instances: list[ScriptedClient] = []
    behaviour: Any = None
    kwargs_seen: list[dict[str, Any]] = []

    def __init__(self, host: str, **kwargs: Any) -> None:
        self.connected = False
        self.closed = False
        type(self).instances.append(self)
        type(self).kwargs_seen.append(kwargs)

    async def connect(self) -> bool:
        self.connected = True
        return True

    def close(self) -> None:
        self.connected = False
        self.closed = True

    async def read_holding_registers(self, address: int, count: int, **_kw: Any) -> Any:
        return await type(self).behaviour(self, address, count)

    async def read_input_registers(self, address: int, count: int, **_kw: Any) -> Any:
        return await type(self).behaviour(self, address, count)

    async def write_register(self, address: int, value: int, **_kw: Any) -> Any:
        return await type(self).behaviour(self, address, 1)


@pytest.fixture(autouse=True)
def scripted_client(monkeypatch: pytest.MonkeyPatch) -> type[ScriptedClient]:
    ScriptedClient.instances = []
    ScriptedClient.kwargs_seen = []

    async def _ok(_client: ScriptedClient, _address: int, count: int) -> Any:
        return _Ok(count)

    ScriptedClient.behaviour = _ok
    monkeypatch.setattr(hub_module, "_ensure_pymodbus", lambda: (ScriptedClient, FakeModbusError))
    monkeypatch.setattr(hub_module, "RETRY_BACKOFF", 0)
    return ScriptedClient


def _bridge(*registers: RegisterDefinition) -> ModbusBridge:
    return ModbusBridge("wallbox", 502, 255, read_timeout=0.5, registers=registers or (CORE,))


async def test_pymodbus_reconnect_and_retries_are_disabled() -> None:
    """The bridge is the only retry/reconnect layer."""

    bridge = _bridge()
    await bridge.async_connect()

    assert ScriptedClient.kwargs_seen[0]["reconnect_delay"] == 0
    assert ScriptedClient.kwargs_seen[0]["retries"] == 0
    await bridge.async_close()


async def test_failed_request_closes_its_client() -> None:
    """Every client that hit a transport error is closed, none is left connected."""

    async def _broken(_client: ScriptedClient, _address: int, _count: int) -> Any:
        raise FakeModbusError("connection reset")

    ScriptedClient.behaviour = _broken
    bridge = _bridge()

    with pytest.raises(WebastoModbusError):
        await bridge.async_read_register(CORE)

    assert len(ScriptedClient.instances) == READ_ATTEMPTS
    assert all(client.closed for client in ScriptedClient.instances)
    assert not any(client.connected for client in ScriptedClient.instances)


async def test_write_uses_fewer_attempts_than_read() -> None:
    async def _broken(_client: ScriptedClient, _address: int, _count: int) -> Any:
        raise FakeModbusError("timeout")

    ScriptedClient.behaviour = _broken
    bridge = _bridge()

    with pytest.raises(WebastoModbusError):
        await bridge.async_write_register(get_register("set_current_a"), 10)

    assert len(ScriptedClient.instances) == WRITE_ATTEMPTS


async def test_operation_has_a_total_time_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """A wallbox that never answers can't block a call for minutes."""

    monkeypatch.setattr(hub_module, "OPERATION_TIMEOUT", 0.2)

    async def _hang(_client: ScriptedClient, _address: int, _count: int) -> Any:
        await asyncio.sleep(3600)

    ScriptedClient.behaviour = _hang
    bridge = _bridge()

    async with asyncio.timeout(5):
        with pytest.raises(WebastoModbusError, match="timed out"):
            await bridge.async_read_register(CORE)


async def test_cancellation_is_not_swallowed() -> None:
    """pymodbus turns CancelledError into ModbusIOException; the bridge undoes that."""

    async def _hang_like_pymodbus(_client: ScriptedClient, _address: int, _count: int) -> Any:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError as err:
            raise FakeModbusError("Request cancelled outside library.") from err

    ScriptedClient.behaviour = _hang_like_pymodbus
    bridge = _bridge()

    task = asyncio.create_task(bridge.async_read_register(CORE))
    await asyncio.sleep(0.05)
    task.cancel()
    async with asyncio.timeout(2):
        with pytest.raises(asyncio.CancelledError):
            await task
    assert len(ScriptedClient.instances) == 1


async def test_forced_close_does_not_crash_the_running_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Closing while a request holds the lock gives that request a clean error."""

    monkeypatch.setattr(hub_module, "CLOSE_LOCK_TIMEOUT", 0.05)
    release = asyncio.Event()

    async def _slow_then_closed(client: ScriptedClient, _address: int, _count: int) -> Any:
        await release.wait()
        if client.closed:
            raise FakeModbusError("client closed")
        return _Ok()

    ScriptedClient.behaviour = _slow_then_closed
    bridge = _bridge()
    task = asyncio.create_task(bridge._async_read_register_once(CORE))
    await asyncio.sleep(0.01)

    await bridge.async_close()
    release.set()

    with pytest.raises(WebastoModbusError):
        await task


@pytest.mark.parametrize(("code", "pruned"), [(1, True), (2, True), (5, False), (6, False)])
async def test_optional_block_pruned_only_when_unsupported(code: int, pruned: bool) -> None:
    async def _optional_fails(_client: ScriptedClient, address: int, count: int) -> Any:
        return _Err(code) if address == OPTIONAL.address else _Ok(count)

    ScriptedClient.behaviour = _optional_fails
    bridge = _bridge(CORE, OPTIONAL)

    data = await bridge.async_read_data()

    assert data[OPTIONAL.key] is None
    remaining = [request.start_address for request in bridge._read_plan]
    assert (OPTIONAL.address in remaining) is not pruned
    await bridge.async_close()


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
    writes: list[tuple[int, int]] = []

    async def _wallbox(client: ScriptedClient, address: int, count: int) -> Any:
        result = _Ok(count)
        if address == 2002:
            result.registers = [20]
        elif address == 6000:
            result.registers = [0]
        return result

    async def _write(self: ScriptedClient, address: int, value: int, **_kw: Any) -> Any:
        writes.append((address, value))
        return _Ok()

    ScriptedClient.behaviour = _wallbox
    original_write = ScriptedClient.write_register
    ScriptedClient.write_register = _write  # type: ignore[method-assign]
    try:
        bridge = _bridge()
        interval = await bridge._async_life_bit_cycle()
    finally:
        ScriptedClient.write_register = original_write  # type: ignore[method-assign]

    assert writes == [(6000, 1)]
    assert interval == 10.0
    await bridge.async_close()


async def test_life_bit_backoff_ends_when_wallbox_reachable() -> None:
    bridge = _bridge()

    waiter = asyncio.create_task(bridge._async_wait_reachable(3600))
    await asyncio.sleep(0)
    bridge.notify_reachable()

    async with asyncio.timeout(1):
        await waiter


# --------------------------------------------------------------------------- #
# Real pymodbus against a TCP server that accepts but never answers
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
async def test_real_pymodbus_does_not_leak_connections(
    socket_enabled: None,
    monkeypatch: pytest.MonkeyPatch,
    silent_server: tuple[int, list[asyncio.StreamWriter]],
) -> None:
    """One failed read must not leave sockets or reconnect tasks behind."""

    pymodbus_client = pytest.importorskip("pymodbus.client")
    pymodbus_exceptions = pytest.importorskip("pymodbus.exceptions")
    monkeypatch.setattr(
        hub_module,
        "_ensure_pymodbus",
        lambda: (pymodbus_client.AsyncModbusTcpClient, pymodbus_exceptions.ModbusException),
    )
    port, connections = silent_server
    bridge = ModbusBridge("127.0.0.1", port, 255, read_timeout=0.2, registers=(CORE,))

    with pytest.raises(WebastoModbusError):
        await bridge.async_read_register(CORE)
    await bridge.async_close()
    await asyncio.sleep(0.3)

    open_connections = [w for w in connections if not w.is_closing()]
    # The server sees the client's FIN as EOF and closes its side.
    assert open_connections == []
    reconnect_tasks = [
        task for task in asyncio.all_tasks() if "reconnect" in (task.get_name() or "")
    ]
    assert reconnect_tasks == []
