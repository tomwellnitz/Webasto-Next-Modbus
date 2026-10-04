"""Asynchronous Modbus transport and decoding helpers."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Coroutine, Iterable
from dataclasses import dataclass
from typing import Any, Final, TypeVar

from modbus_connection import (
    ModbusError,
    ModbusExceptionError,
    ModbusTimeoutError,
    ModbusUnit,
)

from .const import (
    REGISTER_TYPE,
    SESSION_COMMAND_IDLE_VALUE,
    SESSION_COMMAND_RESET_DELAY,
    RegisterDefinition,
    get_readable_registers,
    get_register,
)

_LOGGER = logging.getLogger(__name__)

MAX_REGISTERS_PER_REQUEST: Final = 110

# Retry policy of a single bridge operation (read, bulk read, write). Each
# attempt is one request on the shared connection (which does not retry by
# itself), and the whole operation is bounded by OPERATION_TIMEOUT.
READ_ATTEMPTS: Final = 3
WRITE_ATTEMPTS: Final = 2
RETRY_BACKOFF: Final = 1.0  # seconds, multiplied by the attempt number
OPERATION_TIMEOUT: Final = 30.0  # seconds

# Per-request timeout the bridge asks the shared connection for. Only honoured
# from modbus-connection 4.11 on (``ModbusUnit.require_timeout``); older Home
# Assistant cores keep the connection's 10 s default, which OPERATION_TIMEOUT
# still bounds.
REQUEST_TIMEOUT: Final = 5.0  # seconds

# Life bit ("keep-alive"): the spec says the energy manager "writes 1 every
# 1/2 of comTimeout" (register 2002) and the wallbox clears it. A Next on
# firmware 3.1.16 clears it about comTimeout/2 after each write, so right
# before the next write it still holds our 1 and is not read back. The
# interval is clamped so a 0/garbage timeout can't spin the loop and a long
# timeout doesn't leave the wallbox unattended for minutes.
LIFE_BIT_DEFAULT_COM_TIMEOUT: Final = 60  # seconds, if 2002 can't be read
LIFE_BIT_MIN_INTERVAL: Final = 2.0
LIFE_BIT_MAX_INTERVAL: Final = 30.0

# Backoff (seconds) while the wallbox is unreachable. Capped at the longest
# keep-alive interval, and cut short as soon as a data poll succeeds again,
# so a wallbox that comes back is not left in fail-safe for minutes.
LIFE_BIT_BACKOFF_MIN: Final = 2.0
LIFE_BIT_BACKOFF_MAX: Final = LIFE_BIT_MAX_INTERVAL

# Modbus exception codes that mean "this register does not exist here".
# Only these remove an optional block from the read plan; anything else
# (busy, acknowledge, ...) is transient.
_UNSUPPORTED_REGISTER_CODES: Final = frozenset({1, 2})


class WebastoModbusError(Exception):
    """Raised when a Modbus communication error occurs."""


class WebastoModbusDeviceError(WebastoModbusError):
    """Raised when the wallbox answered but returned a Modbus exception.

    Distinct from transport errors (connection refused, timeout, …): the
    device understood the request and rejected it, so closing the connection
    and retrying immediately won't help. Typically seen while the wallbox is
    still booting, or for a register a given firmware doesn't implement.
    """


_MODBUS_EXCEPTION_NAMES: Final[dict[int, str]] = {
    1: "Illegal Function",
    2: "Illegal Data Address",
    3: "Illegal Data Value",
    4: "Server Device Failure",
    5: "Acknowledge",
    6: "Server Device Busy",
    8: "Memory Parity Error",
    10: "Gateway Path Unavailable",
    11: "Gateway Target Device Failed To Respond",
}


def _describe_modbus_exception(err: ModbusExceptionError) -> str:
    """Return a human-readable description of a Modbus exception response."""

    code = err.exception_code
    if code is not None:
        code = int(code)
        return f"exception code {code} ({_MODBUS_EXCEPTION_NAMES.get(code, 'unknown')})"
    return str(err) or repr(err)


@dataclass(slots=True, frozen=True)
class ReadRequest:
    """Aggregate multiple register definitions into a single Modbus read call."""

    start_address: int
    count: int
    register_type: REGISTER_TYPE
    registers: tuple[RegisterDefinition, ...]


def _build_read_plan(definitions: Iterable[RegisterDefinition]) -> tuple[ReadRequest, ...]:
    """Build the read requests for a set of register definitions.

    Registers are grouped by type (input/holding). Only overlapping
    definitions share a request; adjacent registers are deliberately read one
    request each, which is how the integration has always polled the wallbox
    and avoids depending on how a firmware handles reads spanning several
    registers. Blocks of optional registers come last.
    """

    requests: list[ReadRequest] = []
    by_type: dict[REGISTER_TYPE, list[RegisterDefinition]] = {"input": [], "holding": []}

    for definition in definitions:
        by_type[definition.register_type].append(definition)

    for register_type, items in by_type.items():
        if not items:
            continue

        items.sort(key=lambda reg: reg.address)
        current_regs: list[RegisterDefinition] = []
        current_start: int | None = None
        current_end: int | None = None

        for definition in items:
            reg_start = definition.address
            reg_end = definition.address + definition.count

            if (
                current_start is None
                or current_end is None
                or reg_start >= current_end
                or reg_end - current_start > MAX_REGISTERS_PER_REQUEST
            ):
                if current_regs:
                    assert current_start is not None
                    assert current_end is not None
                    requests.append(
                        ReadRequest(
                            start_address=current_start,
                            count=current_end - current_start,
                            register_type=register_type,
                            registers=tuple(current_regs),
                        )
                    )
                current_regs = [definition]
                current_start = reg_start
                current_end = reg_end
            else:
                current_regs.append(definition)
                current_end = max(current_end, reg_end)

        if current_regs and current_start is not None and current_end is not None:
            requests.append(
                ReadRequest(
                    start_address=current_start,
                    count=current_end - current_start,
                    register_type=register_type,
                    registers=tuple(current_regs),
                )
            )

    # Blocks made only of optional registers go last: the first block decides
    # whether the wallbox is reachable at all, so it must be one every firmware
    # implements (see _async_read_data_once).
    requests.sort(
        key=lambda request: (
            all(reg.optional for reg in request.registers),
            request.register_type,
            request.start_address,
        )
    )
    return tuple(requests)


T = TypeVar("T")


def life_bit_interval(com_timeout: object) -> float:
    """Return the keep-alive write interval for a comTimeout value (seconds)."""

    if not isinstance(com_timeout, (int, float)) or com_timeout <= 0:
        com_timeout = LIFE_BIT_DEFAULT_COM_TIMEOUT
    return float(min(max(com_timeout / 2, LIFE_BIT_MIN_INTERVAL), LIFE_BIT_MAX_INTERVAL))


class ModbusBridge:
    """Read and write wallbox registers over a Modbus unit.

    The unit comes from Home Assistant's ``modbus`` integration
    (``async_get_unit`` / ``async_get_temporary_unit``), which owns the TCP
    connection: it connects on the first request, reconnects on the next
    request after the link dropped, serialises the requests of every
    integration talking to the same wallbox, and closes the socket when the
    last holder lets go. The bridge adds the register map, decoding, bounded
    retries and the life-bit loop on top.
    """

    def __init__(
        self,
        unit: ModbusUnit,
        *,
        host: str,
        port: int,
        unit_id: int,
        registers: tuple[RegisterDefinition, ...] | None = None,
    ) -> None:
        self._unit = unit
        self._host = host
        self._port = port
        self._unit_id = unit_id
        require_timeout = getattr(unit, "require_timeout", None)
        if callable(require_timeout):
            require_timeout(REQUEST_TIMEOUT)
        self._readable_registers: tuple[RegisterDefinition, ...] = (
            tuple(registers) if registers is not None else get_readable_registers()
        )
        self._read_plan: tuple[ReadRequest, ...] = _build_read_plan(self._readable_registers)
        self._life_bit_task: asyncio.Task[None] | None = None
        # Set by the coordinator after a successful poll; wakes the life-bit
        # loop out of its error backoff.
        self._reachable = asyncio.Event()
        # Set by async_close(): the entry is unloading and releases its hold
        # on the shared connection, so no request (not even a retry of one
        # that was in flight) may use the unit afterwards.
        self._closed = False

    # ------------------------------------------------------------------ #
    # Life bit
    # ------------------------------------------------------------------ #

    async def start_life_bit_loop(
        self,
        create_task: Callable[[Coroutine[Any, Any, None]], asyncio.Task[None]] | None = None,
    ) -> None:
        """Start the background life bit loop.

        ``create_task`` lets the caller own the task (Home Assistant passes
        ``entry.async_create_background_task`` so the loop is tracked with the
        config entry and cancelled on unload even if setup fails half-way).
        """
        if self._life_bit_task and not self._life_bit_task.done():
            return
        factory = create_task or asyncio.create_task
        self._life_bit_task = factory(self._life_bit_loop())

    async def stop_life_bit_loop(self) -> None:
        """Stop the background life bit loop."""
        if self._life_bit_task:
            _LOGGER.debug("Stopping life bit loop...")
            self._life_bit_task.cancel()
            try:
                await asyncio.wait_for(self._life_bit_task, timeout=5.0)
            except asyncio.CancelledError:
                pass
            except TimeoutError:
                _LOGGER.warning("Life bit loop did not stop within timeout")
            self._life_bit_task = None
            _LOGGER.debug("Life bit loop stopped")

    def notify_reachable(self) -> None:
        """Tell the life-bit loop that the wallbox answered a data poll."""

        self._reachable.set()

    async def _life_bit_loop(self) -> None:
        """Write the life bit every comTimeout/2, as the Modbus spec requires.

        There is no "wallbox ready" status register: while the wallbox is still
        booting (which can take a couple of minutes) reads and writes come back
        as Modbus exceptions, and a powered-off wallbox refuses the connection.
        Either way the loop backs off, logs the failure once (then at DEBUG),
        and resumes the normal cadence as soon as an operation succeeds or the
        coordinator reports the wallbox reachable again.
        """
        loop = asyncio.get_running_loop()
        backoff = LIFE_BIT_BACKOFF_MIN
        warned = False

        while True:
            cycle_start = loop.time()
            try:
                interval = await self._async_life_bit_cycle()
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 - keep the loop alive
                if not warned:
                    _LOGGER.warning("Life bit loop error (will keep retrying): %s", err)
                    warned = True
                else:
                    _LOGGER.debug("Life bit loop still failing: %s", err)
                await self._async_wait_reachable(backoff)
                backoff = min(backoff * 2, LIFE_BIT_BACKOFF_MAX)
                continue

            if warned:
                _LOGGER.info("Life bit loop recovered")
                warned = False
            backoff = LIFE_BIT_BACKOFF_MIN
            # Fixed schedule: the time the cycle itself took counts against
            # the interval, so slow responses don't stretch it past comTimeout.
            await asyncio.sleep(max(0.0, interval - (loop.time() - cycle_start)))

    async def _async_life_bit_cycle(self) -> float:
        """Write the life bit once and return the interval until the next write."""

        com_timeout: int | float | str | None = None
        # A failed read must not keep the write below from happening: the
        # write is what keeps the wallbox out of fail-safe.
        try:
            com_timeout = await self.async_read_register(get_register("failsafe_timeout_s"))
        except WebastoModbusError as err:
            _LOGGER.debug("Reading the fail-safe timeout failed, using the default: %s", err)
        interval = life_bit_interval(com_timeout)

        await self.async_write_register(get_register("send_keepalive"), 1)
        return interval

    async def _async_wait_reachable(self, delay: float) -> None:
        """Sleep up to ``delay`` seconds, waking early on notify_reachable()."""

        self._reachable.clear()
        try:
            async with asyncio.timeout(delay):
                await self._reachable.wait()
        except TimeoutError:
            pass

    # ------------------------------------------------------------------ #
    # Requests
    # ------------------------------------------------------------------ #

    async def _request(self, func: Callable[[], Awaitable[T]], description: str) -> T:
        """Run one unit request, mapping transport failures to WebastoModbusError.

        Modbus exception responses (``ModbusExceptionError``) are left to the
        caller, which knows whether a rejected register is fatal.
        """

        if self._closed:
            raise WebastoModbusError(f"Connection to {self._host} has been closed")
        try:
            return await func()
        except ModbusExceptionError:
            raise
        except ModbusTimeoutError as err:
            # The link is up but the wallbox stopped answering (e.g. it lost
            # power without closing the socket). Drop the link so the next
            # attempt opens a fresh one instead of waiting on a dead peer.
            with contextlib.suppress(ModbusError, OSError):
                await self._unit.disconnect()
            raise WebastoModbusError(f"{description} timed out ({self.endpoint})") from err
        except (ModbusError, OSError) as err:
            # Connection refused or lost (another client may hold the
            # wallbox's only Modbus TCP slot), or a protocol error. The
            # connection reconnects by itself on the next request.
            raise WebastoModbusError(f"{description} failed ({self.endpoint}): {err}") from err

    async def _read_block(
        self, register_type: REGISTER_TYPE, address: int, count: int
    ) -> list[int]:
        if register_type == "input":
            return await self._request(
                lambda: self._unit.read_input_registers(address, count),
                f"reading input registers @{address}",
            )
        return await self._request(
            lambda: self._unit.read_holding_registers(address, count),
            f"reading holding registers @{address}",
        )

    async def async_close(self) -> None:
        """Stop using the unit; the bridge does not send requests afterwards.

        The connection itself belongs to Home Assistant's ``modbus``
        integration and is released with the config entry, so it is not
        closed here (another integration may share it).
        """

        _LOGGER.debug("Closing the Modbus bridge for %s", self.endpoint)
        self._closed = True

    # ------------------------------------------------------------------ #
    # Public operations
    # ------------------------------------------------------------------ #

    async def async_test_connection(self) -> None:
        """Read one register once to validate the connection.

        No retries, so a config flow gets a quick answer for an unreachable or
        occupied wallbox.
        """

        if not self._readable_registers:
            return
        await self._async_read_register_once(self._readable_registers[0])

    async def async_read_register(self, register: RegisterDefinition) -> int | float | str | None:
        """Read a single register definition and return the decoded value."""

        return await self._call_with_retry(
            lambda: self._async_read_register_once(register),
            f"read register {register.key}",
            READ_ATTEMPTS,
        )

    async def async_read_data(self) -> dict[str, float | int | str | None]:
        """Read all relevant registers and return a dictionary."""

        return await self._call_with_retry(self._async_read_data_once, "bulk read", READ_ATTEMPTS)

    async def async_write_register(self, register: RegisterDefinition, value: int) -> None:
        """Write a single holding register."""

        if not register.writable:
            raise ValueError(f"Register {register.key} is not writable")

        await self._call_with_retry(
            lambda: self._async_write_register_once(register, value),
            f"write register {register.key}",
            WRITE_ATTEMPTS,
        )

    async def async_send_session_command(self, value: int) -> None:
        """Start (1) or cancel (2) a charging session via register 5006.

        The wallbox only acts when the register value changes, so a second
        start after an earlier one would be ignored if we wrote 1 again. Write
        the idle value first so every command produces the required edge.
        """

        register = get_register("session_command")
        await self.async_write_register(register, SESSION_COMMAND_IDLE_VALUE)
        await asyncio.sleep(SESSION_COMMAND_RESET_DELAY)
        await self.async_write_register(register, value)

    async def _call_with_retry(
        self,
        func: Callable[[], Awaitable[T]],
        description: str,
        attempts: int,
    ) -> T:
        """Run ``func`` with a bounded number of attempts and a total time budget."""

        last_err: WebastoModbusError | None = None
        try:
            async with asyncio.timeout(OPERATION_TIMEOUT):
                for attempt in range(1, attempts + 1):
                    try:
                        return await func()
                    except WebastoModbusDeviceError:
                        # The wallbox answered and rejected the request.
                        # Retrying won't change the answer.
                        raise
                    except WebastoModbusError as err:
                        last_err = err
                        # Per-attempt detail at DEBUG only: the caller
                        # (coordinator / life-bit loop) logs the failure once.
                        _LOGGER.debug(
                            "Attempt %s/%s to %s failed: %s", attempt, attempts, description, err
                        )
                        if self._closed:
                            break
                        if attempt < attempts:
                            await asyncio.sleep(RETRY_BACKOFF * attempt)
        except TimeoutError as err:
            # The budget ran out, usually while a request was still waiting on
            # a silent peer (the cancelled request never reaches _request's
            # timeout handling). Drop the link here too.
            with contextlib.suppress(ModbusError, OSError):
                await self._unit.disconnect()
            raise WebastoModbusError(
                f"{description} timed out after {OPERATION_TIMEOUT:.0f} s"
            ) from err
        assert last_err is not None
        raise last_err

    async def _async_read_register_once(
        self,
        register: RegisterDefinition,
    ) -> int | float | str | None:
        try:
            registers = await self._read_block(
                register.register_type, register.address, register.count
            )
        except ModbusExceptionError as err:
            raise WebastoModbusDeviceError(
                f"reading {register.key} (@{register.address}) failed: "
                f"{_describe_modbus_exception(err)}"
            ) from err

        return _decode_register(register, registers)

    async def _async_read_data_once(self) -> dict[str, float | int | str | None]:
        data: dict[str, float | int | str | None] = {}

        read_any = False
        for request in self._read_plan:
            try:
                registers = await self._read_block(
                    request.register_type, request.start_address, request.count
                )
            except ModbusExceptionError as err:
                detail = _describe_modbus_exception(err)
                optional_block = all(reg.optional for reg in request.registers)
                if not read_any and not optional_block:
                    # The first (core) block came back as an error: the
                    # wallbox is offline or still booting. Don't bother with
                    # the remaining blocks (they'll fail too) and let the
                    # coordinator emit a single "not responding" log line.
                    raise WebastoModbusDeviceError(
                        f"wallbox not responding (read @{request.start_address} returned {detail})"
                    ) from err
                code = err.exception_code
                if optional_block and code is not None and int(code) in _UNSUPPORTED_REGISTER_CODES:
                    # This firmware doesn't implement the register.
                    _LOGGER.info(
                        "Removing optional register block @%s from read plan "
                        "(not supported by this wallbox: %s)",
                        request.start_address,
                        detail,
                    )
                    self._read_plan = tuple(r for r in self._read_plan if r is not request)
                elif optional_block:
                    _LOGGER.debug(
                        "Optional register block @%s temporarily failed: %s",
                        request.start_address,
                        detail,
                    )
                else:
                    _LOGGER.warning(
                        "Modbus error reading block @%s (%s): %s",
                        request.start_address,
                        request.count,
                        detail,
                    )
                for definition in request.registers:
                    data[definition.key] = None
                continue

            read_any = True
            for definition in request.registers:
                offset = definition.address - request.start_address
                slice_end = offset + definition.count
                register_values = registers[offset:slice_end]
                if len(register_values) != definition.count:
                    _LOGGER.warning(
                        "Received %s values for %s, expected %s",
                        len(register_values),
                        definition.key,
                        definition.count,
                    )
                    data[definition.key] = None
                    continue
                data[definition.key] = _decode_register(definition, register_values)

        return data

    async def _async_write_register_once(self, register: RegisterDefinition, value: int) -> None:
        try:
            await self._request(
                lambda: self._unit.write_register(register.address, value),
                f"writing {register.key} (@{register.address})",
            )
        except ModbusExceptionError as err:
            raise WebastoModbusDeviceError(
                f"writing {register.key} (@{register.address}) failed: "
                f"{_describe_modbus_exception(err)}"
            ) from err

    @property
    def host(self) -> str:
        """Return the configured Modbus host."""

        return self._host

    @property
    def unit_id(self) -> int:
        """Return the configured Modbus unit / device id."""

        return self._unit_id

    @property
    def endpoint(self) -> str:
        """Return the Modbus endpoint for logging/diagnostics."""

        return f"{self._host}:{self._port} (device_id {self._unit_id})"


def _decode_register(definition: RegisterDefinition, data: list[int]) -> float | int | str:
    """Decode a Modbus response into a Python value."""

    if definition.data_type == "string":
        byte_buffer = bytearray()
        for register in data:
            byte_buffer.extend(register.to_bytes(2, "big"))
        byte_buffer = byte_buffer.rstrip(b"\x00")
        text = byte_buffer.decode(
            definition.encoding or "utf-8",
            errors="ignore",
        )
        return text.strip()

    if definition.data_type == "uint16":
        raw_value = data[0]
    elif definition.data_type == "uint32":
        raw_value = (data[0] << 16) + data[1]
    else:  # pragma: no cover - defensive fallback
        raise ValueError(f"Unsupported data type: {definition.data_type}")

    value = raw_value * definition.scale
    if definition.scale == 1:
        # Return integer for whole numbers to keep entity states clean.
        return int(value)
    return value
