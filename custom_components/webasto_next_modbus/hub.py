"""Asynchronous Modbus transport and decoding helpers."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any, Final, TypeVar, cast

from .const import (
	MAX_RETRY_ATTEMPTS,
	REGISTER_TYPE,
	RETRY_BACKOFF_SECONDS,
	RegisterDefinition,
	all_registers,
)

try:  # pragma: no cover - optional dependency import
	from pymodbus.client import AsyncModbusTcpClient as _AsyncModbusTcpClient
	from pymodbus.exceptions import ModbusException as _ModbusException
except ImportError:  # pragma: no cover - handled at runtime
	_AsyncModbusTcpClient = None  # type: ignore[assignment]
	_ModbusException = None  # type: ignore[assignment]

_ASYNC_CLIENT_CLASS: type[Any] | None = cast("type[Any] | None", _AsyncModbusTcpClient)
_MODBUS_EXCEPTION_CLASS: type[Exception] | None = cast("type[Exception] | None", _ModbusException)

_LOGGER = logging.getLogger(__name__)

MAX_REGISTERS_PER_REQUEST: Final = 110


class WebastoModbusError(Exception):
	"""Raised when a Modbus communication error occurs."""


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

	global _ASYNC_CLIENT_CLASS, _MODBUS_EXCEPTION_CLASS
	if _ASYNC_CLIENT_CLASS is None or _MODBUS_EXCEPTION_CLASS is None:
		raise RuntimeError(
			"pymodbus is required for the Webasto Next Modbus integration. "
			"Install it by adding 'pymodbus' to your environment."
		)

	return cast(type[Any], _ASYNC_CLIENT_CLASS), cast(type[Exception], _MODBUS_EXCEPTION_CLASS)


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
		self._read_plan = _build_read_plan(all_registers(include_write_only=False))
	async def _invoke_with_unit(
		self,
		method: Callable[..., Awaitable[Any]],
		*args: Any,
		**kwargs: Any,
	) -> Any:
		"""Call a pymodbus coroutine, handling differing unit keyword names."""

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
						"Modbus client does not support unit/slave parameter"
					) from err_positional
				raise WebastoModbusError(str(err_positional)) from err_positional

		raise WebastoModbusError("Modbus client does not support unit/slave parameter")

	@staticmethod
	def _is_keyword_unsupported(err: TypeError, keyword: str) -> bool:
		"""Return True if TypeError indicates an unexpected keyword argument."""

		message = str(err)
		return (
			"unexpected keyword argument" in message and f"'{keyword}'" in message
			or "multiple values for argument" in message and f"'{keyword}'" in message
		)

	@staticmethod
	def _is_positional_only_error(err: TypeError) -> bool:
		"""Detect positional argument mismatches when falling back."""

		message = str(err)
		return "positional argument" in message and "given" in message

	async def async_connect(self) -> None:
		"""Initialise the Modbus client connection."""

		if self._client and getattr(self._client, "connected", False):
			return

		client = self._client_cls(self._host, port=self._port, timeout=self._timeout)
		await client.connect()
		if not client.connected:
			raise WebastoModbusError(
				f"Unable to connect to {self._host}:{self._port} (unit {self._unit_id})"
			)
		self._client = client
		_LOGGER.debug("Modbus connection established to %s:%s", self._host, self._port)

	async def async_close(self) -> None:
		"""Close the Modbus connection."""

		if self._client is not None:
			close_result = self._client.close()
			if inspect.isawaitable(close_result):
				await close_result
			self._client = None
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
			except WebastoModbusError as err:
				last_err = err
				_LOGGER.warning(
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

	async def _async_read_register_once(self, register: RegisterDefinition) -> int | float | None:
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
			except modbus_exception as err:  # type: ignore[misc]
				raise WebastoModbusError(str(err)) from err

		if not hasattr(response, "isError") or response.isError():  # type: ignore[attr-defined]
			raise WebastoModbusError(
				f"Modbus error reading {register.key} (address {register.address})"
			)

		return _decode_register(register, response.registers)  # type: ignore[attr-defined]

	async def _async_read_data_once(self) -> dict[str, float | int | str | None]:
		data: dict[str, float | int | str | None] = {}
		modbus_exception = self._modbus_exception

		async with self._lock:
			await self.async_connect()
			assert self._client is not None

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
				except modbus_exception as err:  # type: ignore[misc]
					raise WebastoModbusError(str(err)) from err

				if response.isError():  # type: ignore[attr-defined]
					raise WebastoModbusError(
						f"Modbus error reading block @{request.start_address} ({request.count})"
					)

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
			except modbus_exception as err:  # type: ignore[misc]
				raise WebastoModbusError(str(err)) from err

		if response.isError():  # type: ignore[attr-defined]
			raise WebastoModbusError(
				f"Writing register {register.key} failed: {response!r}"  # type: ignore[str-format]
			)

	@property
	def endpoint(self) -> str:
		"""Return the Modbus endpoint for logging/diagnostics."""

		return f"{self._host}:{self._port} (unit {self._unit_id})"



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
