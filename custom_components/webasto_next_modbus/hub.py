"""Asynchronous Modbus transport and decoding helpers."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable, Coroutine, Iterable
from dataclasses import dataclass
from typing import Any, Final, TypeVar, cast

from .const import (
    REGISTER_TYPE,
    SESSION_COMMAND_IDLE_VALUE,
    SESSION_COMMAND_RESET_DELAY,
    RegisterDefinition,
    get_readable_registers,
    get_register,
)

try:  # pragma: no cover - optional dependency import
    from pymodbus.client import AsyncModbusTcpClient as _AsyncModbusTcpClient
    from pymodbus.exceptions import ModbusException as _ModbusException
except ImportError:  # pragma: no cover - handled at runtime
    _AsyncModbusTcpClient = None  # type: ignore[assignment, misc]
    _ModbusException = None  # type: ignore[assignment, misc]

_LOGGER = logging.getLogger(__name__)

MAX_REGISTERS_PER_REQUEST: Final = 110

# Retry policy of a single bridge operation (read, bulk read, write). Each
# attempt is one Modbus request with the bridge's request timeout; pymodbus'
# own per-request retries are disabled so this is the only retry layer, and
# the whole operation is bounded by OPERATION_TIMEOUT.
READ_ATTEMPTS: Final = 3
WRITE_ATTEMPTS: Final = 2
RETRY_BACKOFF: Final = 1.0  # seconds, multiplied by the attempt number
OPERATION_TIMEOUT: Final = 30.0  # seconds

# Waiting for the lock before a forced close on unload (seconds).
CLOSE_LOCK_TIMEOUT: Final = 2.0
CLIENT_CLOSE_TIMEOUT: Final = 3.0

# Life bit ("keep-alive"): the spec says the energy manager "writes 1 every
# 1/2 of comTimeout" (register 2002) and the wallbox clears it. The interval
# is clamped so a 0/garbage timeout can't spin the loop and a long timeout
# doesn't leave the wallbox unattended for minutes.
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


def _describe_modbus_response(response: Any) -> str:
    """Return a human-readable description of an error response."""

    code = getattr(response, "exception_code", None)
    if isinstance(code, int):
        return f"exception code {code} ({_MODBUS_EXCEPTION_NAMES.get(code, 'unknown')})"
    text = str(response)
    if text and "object at 0x" not in text:
        return text
    return repr(response)


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


def _ensure_pymodbus() -> tuple[type[Any], type[Exception]]:
    """Ensure pymodbus is imported and return the relevant classes."""

    if _AsyncModbusTcpClient is None or _ModbusException is None:
        raise RuntimeError(
            "pymodbus is required for the Webasto Next Modbus integration. "
            "Install it by adding 'pymodbus' to your environment."
        )

    return cast(type[Any], _AsyncModbusTcpClient), cast(type[Exception], _ModbusException)


T = TypeVar("T")


def life_bit_interval(com_timeout: object) -> float:
    """Return the keep-alive write interval for a comTimeout value (seconds)."""

    if not isinstance(com_timeout, (int, float)) or com_timeout <= 0:
        com_timeout = LIFE_BIT_DEFAULT_COM_TIMEOUT
    return float(min(max(com_timeout / 2, LIFE_BIT_MIN_INTERVAL), LIFE_BIT_MAX_INTERVAL))


async def _async_close_client(client: Any) -> None:
    """Close a pymodbus client, whether its ``close`` is sync or async."""

    try:
        result = client.close()
        if inspect.isawaitable(result):
            await asyncio.wait_for(result, timeout=CLIENT_CLOSE_TIMEOUT)
    except Exception as err:  # noqa: BLE001 - closing must never raise
        _LOGGER.debug("Error closing Modbus client: %s", err)


def _raise_if_cancelled(err: BaseException) -> None:
    """Re-raise a cancellation that pymodbus converted into a ModbusIOException.

    pymodbus catches ``CancelledError`` inside a pending request and raises
    ``ModbusIOException("Request cancelled outside library")`` instead. If we
    treated that as a transport error, unload, ``asyncio.timeout`` and
    ``asyncio.wait_for`` around a bridge call would be swallowed and retried.
    """

    task = asyncio.current_task()
    if isinstance(err.__cause__, asyncio.CancelledError) or (
        task is not None and task.cancelling()
    ):
        raise asyncio.CancelledError from err


class ModbusBridge:
    """Handle Modbus TCP communication with the wallbox."""

    def __init__(
        self,
        host: str,
        port: int,
        unit_id: int,
        read_timeout: float = 5.0,
        registers: tuple[RegisterDefinition, ...] | None = None,
    ) -> None:
        client_cls, exception_cls = _ensure_pymodbus()

        self._host = host
        self._port = port
        self._unit_id = unit_id
        self._timeout = read_timeout
        self._client_cls = client_cls
        self._modbus_exception = exception_cls
        self._client: Any | None = None
        self._lock = asyncio.Lock()
        self._readable_registers: tuple[RegisterDefinition, ...] = (
            tuple(registers) if registers is not None else get_readable_registers()
        )
        self._read_plan: tuple[ReadRequest, ...] = _build_read_plan(self._readable_registers)
        self._life_bit_task: asyncio.Task[None] | None = None
        # Set by the coordinator after a successful poll; wakes the life-bit
        # loop out of its error backoff.
        self._reachable = asyncio.Event()
        # Set by async_close(): the bridge is being torn down and must not
        # reconnect, not even from a retry of a request that was in flight.
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

        life_bit_reg = get_register("send_keepalive")
        com_timeout: int | float | str | None = None
        # Neither read may keep the write below from happening: the write is
        # what keeps the wallbox out of fail-safe, and it reconnects by itself.
        try:
            com_timeout = await self.async_read_register(get_register("failsafe_timeout_s"))
        except WebastoModbusError as err:
            _LOGGER.debug("Reading the fail-safe timeout failed, using the default: %s", err)
        interval = life_bit_interval(com_timeout)

        try:
            if await self.async_read_register(life_bit_reg) == 1:
                # Diagnostic only: the wallbox should have cleared our last write.
                _LOGGER.debug("Life bit still set from the previous write")
        except WebastoModbusError as err:
            _LOGGER.debug("Reading back the life bit failed: %s", err)

        await self.async_write_register(life_bit_reg, 1)
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
    # pymodbus call helpers
    # ------------------------------------------------------------------ #

    async def _invoke_with_unit(
        self,
        method: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Call a pymodbus coroutine, handling differing device_id keyword names."""

        base_kwargs = dict(kwargs)
        for keyword in ("device_id", "unit", "slave"):
            current_kwargs = dict(base_kwargs)
            if keyword in current_kwargs:
                continue
            current_kwargs[keyword] = self._unit_id
            try:
                return await method(*args, **current_kwargs)
            except TypeError as err_keyword:
                if self._is_keyword_unsupported(err_keyword, keyword):
                    continue
                raise WebastoModbusError(str(err_keyword)) from err_keyword

        if not base_kwargs:
            try:
                return await method(*args, self._unit_id)
            except TypeError as err_positional:
                if self._is_positional_only_error(err_positional):
                    raise WebastoModbusError(
                        "Modbus client does not support device_id/unit/slave parameter"
                    ) from err_positional
                raise WebastoModbusError(str(err_positional)) from err_positional

        raise WebastoModbusError("Modbus client does not support device_id/unit/slave parameter")

    @staticmethod
    def _is_keyword_unsupported(err: TypeError, keyword: str) -> bool:
        """Return True if TypeError indicates an unexpected keyword argument."""

        message = str(err)
        return ("unexpected keyword argument" in message and f"'{keyword}'" in message) or (
            "multiple values for argument" in message and f"'{keyword}'" in message
        )

    @staticmethod
    def _is_positional_only_error(err: TypeError) -> bool:
        """Detect positional argument mismatches when falling back."""

        message = str(err)
        return "positional argument" in message and "given" in message

    # ------------------------------------------------------------------ #
    # Connection handling
    # ------------------------------------------------------------------ #

    async def async_connect(self) -> None:
        """Open the Modbus connection (no-op if it is already open)."""

        async with self._lock:
            await self._async_ensure_connected()

    async def _async_ensure_connected(self) -> Any:
        """Return a connected client, (re)connecting if needed. Caller holds the lock."""

        if self._closed:
            raise WebastoModbusError(f"Connection to {self._host} has been closed")

        client = self._client
        if client is not None and getattr(client, "connected", False):
            return client

        if client is not None:
            # A client that lost its connection still owns a socket (and, on
            # older setups, a reconnect task): close it before replacing it,
            # the wallbox only accepts a single Modbus TCP connection.
            _LOGGER.debug("Closing stale client before reconnect to %s", self._host)
            self._client = None
            await _async_close_client(client)

        try:
            # The bridge does its own reconnecting and retrying: disable the
            # pymodbus equivalents, which would otherwise keep orphaned
            # reconnect tasks alive and multiply every timeout.
            client = self._client_cls(
                self._host,
                port=self._port,
                timeout=self._timeout,
                reconnect_delay=0,
                retries=0,
            )
        except TypeError:
            # Fallback for clients without those keywords (test doubles).
            client = self._client_cls(
                self._host,
                port=self._port,
                timeout=self._timeout,
            )
        try:
            await asyncio.wait_for(client.connect(), timeout=self._timeout)
        except TimeoutError as err:
            await _async_close_client(client)
            raise WebastoModbusError(f"Connection to {self._host}:{self._port} timed out") from err
        except (OSError, self._modbus_exception) as err:
            await _async_close_client(client)
            raise WebastoModbusError(
                f"Failed to connect to {self._host}:{self._port}: {err}"
            ) from err

        if not client.connected:
            await _async_close_client(client)
            raise WebastoModbusError(
                f"Unable to connect to {self._host}:{self._port} (device_id {self._unit_id})"
            )
        self._client = client
        _LOGGER.debug("Modbus connection established to %s:%s", self._host, self._port)
        return client

    async def _async_execute(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """Run one Modbus request on a connected client. Caller holds the lock.

        On a transport error the client is closed right away (not just
        dropped), so its socket is released before the next attempt connects.
        """

        client = await self._async_ensure_connected()
        try:
            return await self._invoke_with_unit(getattr(client, method_name), *args, **kwargs)
        except (self._modbus_exception, OSError, ConnectionError) as err:
            if self._client is client:
                self._client = None
            await _async_close_client(client)
            _raise_if_cancelled(err)
            raise WebastoModbusError(str(err)) from err

    async def async_close(self) -> None:
        """Close the Modbus connection.

        Final: the bridge does not reconnect afterwards, including retries of
        requests that were still running. Waits briefly for a running request
        to finish. If the lock can't be taken (a request is stuck), the client
        is closed anyway: requests work on their own reference to the client,
        so the holder just sees a connection error instead of crashing.
        """
        _LOGGER.debug("Closing Modbus connection to %s...", self._host)
        self._closed = True
        try:
            async with asyncio.timeout(CLOSE_LOCK_TIMEOUT):
                async with self._lock:
                    client, self._client = self._client, None
        except TimeoutError:
            _LOGGER.warning("Could not acquire lock for close, forcing close for %s", self._host)
            client, self._client = self._client, None

        if client is not None:
            await _async_close_client(client)
            _LOGGER.debug("Modbus connection to %s closed", self._host)

    # ------------------------------------------------------------------ #
    # Public operations
    # ------------------------------------------------------------------ #

    async def async_test_connection(self) -> None:
        """Perform a lightweight read to validate the connection."""

        if not self._readable_registers:
            return
        await self.async_read_register(self._readable_registers[0])

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
            raise WebastoModbusError(
                f"{description} timed out after {OPERATION_TIMEOUT:.0f} s"
            ) from err
        assert last_err is not None
        raise last_err

    async def _async_read_register_once(
        self,
        register: RegisterDefinition,
    ) -> int | float | str | None:
        method = (
            "read_input_registers"
            if register.register_type == "input"
            else ("read_holding_registers")
        )
        async with self._lock:
            response = await self._async_execute(method, register.address, count=register.count)

        if not hasattr(response, "isError") or response.isError():
            raise WebastoModbusDeviceError(
                f"reading {register.key} (@{register.address}) failed: "
                f"{_describe_modbus_response(response)}"
            )

        return _decode_register(register, response.registers)

    async def _async_read_data_once(self) -> dict[str, float | int | str | None]:
        data: dict[str, float | int | str | None] = {}

        async with self._lock:
            read_any = False
            for request in self._read_plan:
                method = (
                    "read_input_registers"
                    if request.register_type == "input"
                    else "read_holding_registers"
                )
                response = await self._async_execute(
                    method, request.start_address, count=request.count
                )

                if response.isError():
                    detail = _describe_modbus_response(response)
                    optional_block = all(reg.optional for reg in request.registers)
                    if not read_any and not optional_block:
                        # The first (core) block came back as an error: the
                        # wallbox is offline or still booting. Don't bother with
                        # the remaining blocks (they'll fail too) and let the
                        # coordinator emit a single "not responding" log line.
                        raise WebastoModbusDeviceError(
                            f"wallbox not responding (read @{request.start_address} "
                            f"returned {detail})"
                        )
                    code = getattr(response, "exception_code", None)
                    if optional_block and code in _UNSUPPORTED_REGISTER_CODES:
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
                registers = response.registers
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
        async with self._lock:
            response = await self._async_execute("write_register", register.address, value)

        if response.isError():
            raise WebastoModbusDeviceError(
                f"writing {register.key} (@{register.address}) failed: "
                f"{_describe_modbus_response(response)}"
            )

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
