"""Asynchronous Modbus transport and decoding helpers."""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any, Final, TypeVar, cast

from .const import (
    MAX_RETRY_ATTEMPTS,
    REGISTER_TYPE,
    RETRY_BACKOFF_SECONDS,
    RegisterDefinition,
    all_registers,
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

# Lower bound for the life-bit polling window. Guards against a 0/garbage
# value in the failsafe-timeout register turning the loop into a tight
# read/write spin that would hammer the wallbox and starve the data poll.
LIFE_BIT_MIN_INTERVAL: Final = 10

# Exponential backoff bounds (seconds) for the life-bit loop while the
# wallbox is unreachable (e.g. powered off, or still booting — which can
# take a couple of minutes on these devices).
LIFE_BIT_BACKOFF_MIN: Final = 5.0
LIFE_BIT_BACKOFF_MAX: Final = 300.0


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
    """Build efficient read requests from register definitions.

    Registers are grouped by type (input/holding) and merged while they remain
    contiguous and fit into the maximum register count supported by the EVSE.
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

    requests.sort(key=lambda request: (request.register_type, request.start_address))
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


class ModbusBridge:
    """Handle Modbus TCP communication with the wallbox."""

    def __init__(
        self,
        host: str,
        port: int,
        unit_id: int,
        read_timeout: float = 5.0,
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
        self._read_plan: tuple[ReadRequest, ...] = _build_read_plan(
            all_registers(include_write_only=False)
        )
        self._life_bit_task: asyncio.Task[None] | None = None

    async def start_life_bit_loop(self) -> None:
        """Start the background life bit loop."""
        if self._life_bit_task and not self._life_bit_task.done():
            return
        self._life_bit_task = asyncio.create_task(self._life_bit_loop())

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

    async def _life_bit_loop(self) -> None:
        """Maintain the wallbox keep-alive ("life bit") register.

        - While the wallbox is unreachable, back off exponentially and log the
          failure only once (then at DEBUG) so a slow boot doesn't flood the log.
        - If the wallbox keeps rejecting the life-bit register itself, give up:
          some firmwares simply don't implement it, and there's no point
          hammering the register on every cycle.
        """
        life_bit_reg = get_register("send_keepalive")
        timeout_reg = get_register("failsafe_timeout_s")

        backoff = LIFE_BIT_BACKOFF_MIN
        warned = False
        device_rejections = 0

        while True:
            try:
                poll_timeout = 60  # default keep-alive window
                try:
                    val = await self.async_read_register(timeout_reg)
                    if isinstance(val, (int, float)):
                        poll_timeout = max(int(val), LIFE_BIT_MIN_INTERVAL)
                except WebastoModbusDeviceError:
                    pass  # firmware quirk reading @2002; use the default window
                # Transport errors here propagate to the handlers below.

                await self.async_write_register(life_bit_reg, 1)

                # Success: reset error state.
                if warned:
                    _LOGGER.info("Life bit loop recovered")
                    warned = False
                backoff = LIFE_BIT_BACKOFF_MIN
                device_rejections = 0

                start_time = time.time()
                while time.time() - start_time < poll_timeout:
                    try:
                        if await self.async_read_register(life_bit_reg) == 0:
                            _LOGGER.debug("Life bit cleared after %.2f s", time.time() - start_time)
                            break
                    except WebastoModbusError:
                        break  # don't spin re-reading; the next cycle handles it
                    await asyncio.sleep(1)

                # Floor between keep-alive cycles so a fast-clearing life bit
                # cannot turn this into a tight write loop.
                await asyncio.sleep(1)

            except asyncio.CancelledError:
                raise
            except WebastoModbusDeviceError as err:
                device_rejections += 1
                if device_rejections >= 3:
                    _LOGGER.info(
                        "Wallbox rejected the life-bit register (@%s) repeatedly (%s); "
                        "disabling the keep-alive loop until the integration reloads",
                        life_bit_reg.address,
                        err,
                    )
                    return
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, LIFE_BIT_BACKOFF_MAX)
            except Exception as err:  # noqa: BLE001 - keep the loop alive
                if not warned:
                    _LOGGER.warning("Life bit loop error (will keep retrying): %s", err)
                    warned = True
                else:
                    _LOGGER.debug("Life bit loop still failing: %s", err)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, LIFE_BIT_BACKOFF_MAX)

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
        return (
            "unexpected keyword argument" in message
            and f"'{keyword}'" in message
            or "multiple values for argument" in message
            and f"'{keyword}'" in message
        )

    @staticmethod
    def _is_positional_only_error(err: TypeError) -> bool:
        """Detect positional argument mismatches when falling back."""

        message = str(err)
        return "positional argument" in message and "given" in message

    async def async_connect(self) -> None:
        """Initialise the Modbus client connection."""

        # Check if already connected
        if self._client is not None and getattr(self._client, "connected", False):
            return

        # Close any existing client before creating a new one
        # This prevents orphaned connections from blocking the port
        if self._client is not None:
            _LOGGER.debug("Closing stale client before reconnect to %s", self._host)
            try:
                old_client = self._client
                self._client = None
                close_result = old_client.close()
                if inspect.isawaitable(close_result):
                    await asyncio.wait_for(close_result, timeout=2.0)
            except Exception as err:
                _LOGGER.debug("Error closing stale client: %s", err)

        # Create new client - try with reconnect parameters first, fall back if not supported
        try:
            client = self._client_cls(
                self._host,
                port=self._port,
                timeout=self._timeout,
                reconnect_delay=1.0,
                reconnect_delay_max=30.0,
            )
        except TypeError:
            # Fallback for older pymodbus versions or mock clients
            client = self._client_cls(
                self._host,
                port=self._port,
                timeout=self._timeout,
            )
        try:
            await asyncio.wait_for(client.connect(), timeout=self._timeout)
        except TimeoutError as err:
            # Ensure client is closed on timeout
            try:
                client.close()
            except Exception:
                pass
            raise WebastoModbusError(f"Connection to {self._host}:{self._port} timed out") from err
        except (OSError, self._modbus_exception) as err:
            # Ensure client is closed on error
            try:
                client.close()
            except Exception:
                pass
            raise WebastoModbusError(
                f"Failed to connect to {self._host}:{self._port}: {err}"
            ) from err

        if not client.connected:
            try:
                client.close()
            except Exception:
                pass
            raise WebastoModbusError(
                f"Unable to connect to {self._host}:{self._port} (device_id {self._unit_id})"
            )
        self._client = client
        _LOGGER.debug("Modbus connection established to %s:%s", self._host, self._port)

    async def async_close(self) -> None:
        """Close the Modbus connection."""
        _LOGGER.debug("Closing Modbus connection to %s...", self._host)
        # Use a short timeout for acquiring the lock to avoid blocking shutdown
        try:
            async with asyncio.timeout(2.0):
                async with self._lock:
                    client = self._client
                    self._client = None
        except TimeoutError:
            _LOGGER.warning("Could not acquire lock for close, forcing close for %s", self._host)
            client = self._client
            self._client = None

        if client is not None:
            try:
                close_result = client.close()
                if inspect.isawaitable(close_result):
                    await asyncio.wait_for(close_result, timeout=3.0)
            except TimeoutError:
                _LOGGER.warning("Modbus close timed out for %s", self._host)
            except Exception as err:
                _LOGGER.warning("Error closing Modbus connection: %s", err)
            _LOGGER.debug("Modbus connection to %s closed", self._host)

    async def async_test_connection(self) -> None:
        """Perform a lightweight read to validate the connection."""

        registers = all_registers(include_write_only=False)
        if not registers:
            return
        test_register = registers[0]
        await self.async_read_register(test_register)

    async def async_read_register(self, register: RegisterDefinition) -> int | float | str | None:
        """Read a single register definition and return the decoded value."""

        return await self._call_with_retry(
            lambda: self._async_read_register_once(register),
            f"read register {register.key}",
        )

    async def async_read_data(self) -> dict[str, float | int | str | None]:
        """Read all relevant registers and return a dictionary."""

        return await self._call_with_retry(self._async_read_data_once, "bulk read")

    async def async_write_register(self, register: RegisterDefinition, value: int) -> None:
        """Write a single holding register."""

        if not register.writable:
            raise ValueError(f"Register {register.key} is not writable")

        await self._call_with_retry(
            lambda: self._async_write_register_once(register, value),
            f"write register {register.key}",
        )

    async def _call_with_retry(
        self,
        func: Callable[[], Awaitable[T]],
        description: str,
    ) -> T:
        last_err: WebastoModbusError | None = None
        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            try:
                return await func()
            except asyncio.CancelledError:
                # Re-raise cancellation immediately to allow clean shutdown
                raise
            except WebastoModbusDeviceError:
                # The wallbox answered and rejected the request. Reconnecting
                # and retrying won't change the answer, and tearing the socket
                # down here causes pymodbus transaction-id desyncs.
                raise
            except WebastoModbusError as err:
                last_err = err
                # Per-attempt detail at DEBUG only: the caller (coordinator /
                # life-bit loop) logs the aggregate failure once.
                _LOGGER.debug(
                    "Attempt %s/%s to %s failed: %s",
                    attempt,
                    MAX_RETRY_ATTEMPTS,
                    description,
                    err,
                )
                await self.async_close()
                if attempt == MAX_RETRY_ATTEMPTS:
                    break
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
        assert last_err is not None
        raise last_err

    async def _async_read_register_once(
        self,
        register: RegisterDefinition,
    ) -> int | float | str | None:
        modbus_exception = self._modbus_exception
        async with self._lock:
            await self.async_connect()
            assert self._client is not None  # For type checkers

            try:
                if register.register_type == "input":
                    response = await self._invoke_with_unit(
                        self._client.read_input_registers,
                        register.address,
                        count=register.count,
                    )
                else:
                    response = await self._invoke_with_unit(
                        self._client.read_holding_registers,
                        register.address,
                        count=register.count,
                    )
            except (modbus_exception, OSError, ConnectionError) as err:  # type: ignore[misc]
                # Mark client as disconnected to force reconnect on next attempt
                self._client = None
                raise WebastoModbusError(str(err)) from err

        if not hasattr(response, "isError") or response.isError():  # type: ignore[attr-defined]
            raise WebastoModbusDeviceError(
                f"reading {register.key} (@{register.address}) failed: "
                f"{_describe_modbus_response(response)}"
            )

        return _decode_register(register, response.registers)  # type: ignore[attr-defined]

    async def _async_read_data_once(self) -> dict[str, float | int | str | None]:
        data: dict[str, float | int | str | None] = {}
        modbus_exception = self._modbus_exception

        async with self._lock:
            await self.async_connect()
            assert self._client is not None

            read_any = False
            for request in self._read_plan:
                try:
                    if request.register_type == "input":
                        response = await self._invoke_with_unit(
                            self._client.read_input_registers,
                            request.start_address,
                            count=request.count,
                        )
                    else:
                        response = await self._invoke_with_unit(
                            self._client.read_holding_registers,
                            request.start_address,
                            count=request.count,
                        )
                except (modbus_exception, OSError, ConnectionError) as err:  # type: ignore[misc]
                    # Mark client as disconnected to force reconnect on next attempt
                    self._client = None
                    raise WebastoModbusError(str(err)) from err

                if response.isError():  # type: ignore[attr-defined]
                    detail = _describe_modbus_response(response)
                    if not read_any:
                        # The first (core) block came back as an error: the
                        # wallbox is offline or still booting. Don't bother with
                        # the remaining blocks (they'll fail too) and let the
                        # coordinator emit a single "not responding" log line.
                        raise WebastoModbusDeviceError(
                            f"wallbox not responding (read @{request.start_address} "
                            f"returned {detail})"
                        )
                    # A later block failed while others worked -> likely a
                    # register this firmware doesn't implement.
                    if all(reg.optional for reg in request.registers):
                        _LOGGER.info(
                            "Removing optional register block @%s from read plan "
                            "(not supported by this wallbox: %s)",
                            request.start_address,
                            detail,
                        )
                        self._read_plan = tuple(
                            r for r in self._read_plan if r.start_address != request.start_address
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
                registers = response.registers  # type: ignore[attr-defined]
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
        modbus_exception = self._modbus_exception
        async with self._lock:
            await self.async_connect()
            assert self._client is not None

            try:
                response = await self._invoke_with_unit(
                    self._client.write_register,
                    register.address,
                    value,
                )
            except (modbus_exception, OSError, ConnectionError) as err:  # type: ignore[misc]
                # Mark client as disconnected to force reconnect on next attempt
                self._client = None
                raise WebastoModbusError(str(err)) from err

        if response.isError():  # type: ignore[attr-defined]
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
