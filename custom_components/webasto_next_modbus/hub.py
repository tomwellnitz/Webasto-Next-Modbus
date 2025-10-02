"""Asynchronous Modbus transport and decoding helpers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from .const import (
	REGISTER_TYPE,
	RegisterDefinition,
	all_registers,
)

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


class ModbusBridge:
	"""Handle Modbus TCP communication with the wallbox."""

	def __init__(
		self,
		host: str,
		port: int,
		unit_id: int,
		read_timeout: float = 5.0,
	) -> None:
		self._host = host
		self._port = port
		self._unit_id = unit_id
		self._timeout = read_timeout
		self._client: AsyncModbusTcpClient | None = None
		self._lock = asyncio.Lock()
		self._read_plan = _build_read_plan(all_registers(include_write_only=False))

	async def async_connect(self) -> None:
		"""Initialise the Modbus client connection."""

		if self._client and self._client.connected:
			return

		client = AsyncModbusTcpClient(self._host, port=self._port, timeout=self._timeout)
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
			await self._client.close()
			self._client = None
			_LOGGER.debug("Modbus connection to %s closed", self._host)

	async def async_test_connection(self) -> None:
		"""Perform a lightweight read to validate the connection."""

		registers = all_registers(include_write_only=False)
		if not registers:
			return
		test_register = registers[0]
		await self.async_read_register(test_register)

	async def async_read_register(self, register: RegisterDefinition) -> int | float | None:
		"""Read a single register definition and return the decoded value."""

		async with self._lock:
			await self.async_connect()
			assert self._client is not None  # For type checkers

			try:
				if register.register_type == "input":
					response = await self._client.read_input_registers(
						register.address,
						register.count,
						unit=self._unit_id,
					)
				else:
					response = await self._client.read_holding_registers(
						register.address,
						register.count,
						unit=self._unit_id,
					)
			except ModbusException as err:
				raise WebastoModbusError(str(err)) from err

		if not hasattr(response, "isError") or response.isError():  # type: ignore[attr-defined]
			raise WebastoModbusError(
				f"Modbus error reading {register.key} (address {register.address})"
			)

		return _decode_register(register, response.registers)  # type: ignore[attr-defined]

	async def async_read_data(self) -> dict[str, float | int | None]:
		"""Read all relevant registers and return a dictionary."""

		data: dict[str, float | int | None] = {}

		async with self._lock:
			await self.async_connect()
			assert self._client is not None

			for request in self._read_plan:
				try:
					if request.register_type == "input":
						response = await self._client.read_input_registers(
							request.start_address,
							request.count,
							unit=self._unit_id,
						)
					else:
						response = await self._client.read_holding_registers(
							request.start_address,
							request.count,
							unit=self._unit_id,
						)
				except ModbusException as err:
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

	async def async_write_register(self, register: RegisterDefinition, value: int) -> None:
		"""Write a single holding register."""

		if not register.writable:
			raise ValueError(f"Register {register.key} is not writable")

		async with self._lock:
			await self.async_connect()
			assert self._client is not None

			try:
				response = await self._client.write_register(
					register.address,
					value,
					unit=self._unit_id,
				)
			except ModbusException as err:
				raise WebastoModbusError(str(err)) from err

		if response.isError():  # type: ignore[attr-defined]
			raise WebastoModbusError(
				f"Writing register {register.key} failed: {response!r}"  # type: ignore[str-format]
			)


def _decode_register(definition: RegisterDefinition, data: list[int]) -> float | int:
	"""Decode a Modbus response into a Python value."""

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
