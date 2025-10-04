"""Deterministic Modbus simulator for the Webasto Next integration."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from custom_components.webasto_next_modbus.const import (
	BUTTON_REGISTERS,
	CONTROL_REGISTERS,
	NUMBER_REGISTERS,
	SENSOR_REGISTERS,
	SESSION_COMMAND_START_VALUE,
	SESSION_COMMAND_STOP_VALUE,
	RegisterDefinition,
)


class FakeModbusException(Exception):
	"""Raised when simulator usage is incorrect."""


class _FakeReadResult:
	"""Simplified Modbus read response."""

	def __init__(self, registers: list[int]):
		self.registers = registers

	def isError(self) -> bool:  # pragma: no cover - kept for interface parity
		return False


class _FakeWriteResult:
	"""Simplified Modbus write response."""

	def isError(self) -> bool:  # pragma: no cover - kept for interface parity
		return False


@dataclass(slots=True)
class Scenario:
	"""High level scenario description for the virtual wallbox."""

	unit_id: int = 255
	values: Mapping[str, Any] = field(default_factory=dict)
	write_actions: Mapping[str, Mapping[int, Mapping[str, Any]]] = field(default_factory=dict)

	def create_state(self) -> VirtualWallboxState:
		"""Materialise the scenario into a mutable state object."""

		return VirtualWallboxState(
			unit_id=self.unit_id,
			initial_values=self.values,
			write_actions=self.write_actions,
		)


class VirtualWallboxState:
	"""Mutable register storage for a virtual Webasto Next wallbox."""

	def __init__(
		self,
		*,
		unit_id: int = 255,
		initial_values: Mapping[str, Any] | None = None,
		write_actions: Mapping[str, Mapping[int, Mapping[str, Any]]] | None = None,
	) -> None:
		self.unit_id = unit_id
		self._definitions_by_key: dict[str, RegisterDefinition] = {
			definition.key: definition
			for definition in (
				*SENSOR_REGISTERS,
				*NUMBER_REGISTERS,
				*BUTTON_REGISTERS,
				*CONTROL_REGISTERS,
			)
		}
		self._definitions_by_address: dict[tuple[str, int], RegisterDefinition] = {
			(definition.register_type, definition.address): definition
			for definition in self._definitions_by_key.values()
		}
		self._input_registers: dict[int, int] = {}
		self._holding_registers: dict[int, int] = {}
		self._write_actions: dict[str, dict[int, dict[str, Any]]] = {
			key: {int(command): dict(updates) for command, updates in actions.items()}
			for key, actions in (write_actions or {}).items()
		}
		self.reset()
		if initial_values:
			self.apply_values(initial_values)

	def reset(self) -> None:
		"""Reset all register values to zero."""

		self._input_registers.clear()
		self._holding_registers.clear()
		for definition in self._definitions_by_key.values():
			target = (
				self._input_registers
				if definition.register_type == "input"
				else self._holding_registers
			)
			for offset in range(definition.count):
				target.setdefault(definition.address + offset, 0)

	def apply_values(self, updates: Mapping[str, Any]) -> None:
		"""Apply high-level register updates using register keys."""

		for key, value in updates.items():
			self._apply_value(key, value)

	def read_block(self, register_type: str, start_address: int, count: int) -> list[int]:
		"""Return a block of register values for Modbus reads."""

		store = self._input_registers if register_type == "input" else self._holding_registers
		return [store.get(start_address + offset, 0) for offset in range(count)]

	def write_register(self, address: int, value: int) -> None:
		"""Handle a Modbus holding register write."""

		definition = self._definitions_by_address.get(("holding", address))
		stored_value = value & 0xFFFF
		self._holding_registers[address] = stored_value
		if definition is None:
			return

		actions = self._write_actions.get(definition.key)
		if not actions:
			return

		updates = actions.get(stored_value)
		if updates:
			self.apply_values(updates)

	def resolve_address(self, register_type: str, address: int) -> int:
		"""Map potential zero-based addresses to actual register numbers."""

		candidate = (register_type, address)
		if candidate in self._definitions_by_address:
			return address
		candidate = (register_type, address + 1)
		if candidate in self._definitions_by_address:
			return address + 1
		return address

	def _apply_value(self, key: str, value: Any) -> None:
		definition = self._definitions_by_key.get(key)
		if definition is None:
			raise KeyError(f"Unknown register key: {key}")
		raw_values = _encode_value(definition, value)
		target = (
			self._input_registers
			if definition.register_type == "input"
			else self._holding_registers
		)
		for offset, raw in enumerate(raw_values):
			target[definition.address + offset] = raw


class VirtualWallboxRegistry:
	"""Keep track of simulator instances keyed by host/port/unit_id."""

	def __init__(self) -> None:
		self._states: dict[tuple[str, int], dict[int, VirtualWallboxState]] = {}

	def register(self, host: str, port: int, unit_id: int, state: VirtualWallboxState) -> None:
		key = (host, port)
		bucket = self._states.setdefault(key, {})
		if unit_id in bucket:
			raise ValueError(f"Virtual wallbox already registered for {host}:{port}/{unit_id}")
		bucket[unit_id] = state

	def unregister(self, host: str, port: int, unit_id: int) -> None:
		bucket = self._states.get((host, port))
		if not bucket:
			return
		bucket.pop(unit_id, None)
		if not bucket:
			self._states.pop((host, port), None)

	def get(self, host: str, port: int, unit_id: int) -> VirtualWallboxState | None:
		bucket = self._states.get((host, port))
		if not bucket:
			return None
		return bucket.get(unit_id)

	def require(self, host: str, port: int, unit_id: int) -> VirtualWallboxState:
		state = self.get(host, port, unit_id)
		if state is None:
			raise FakeModbusException(
				f"No virtual wallbox registered for {host}:{port} (unit {unit_id})"
			)
		return state

	def has_endpoint(self, host: str, port: int) -> bool:
		return (host, port) in self._states

	def clear(self) -> None:
		self._states.clear()


registry = VirtualWallboxRegistry()


@contextmanager
def register_virtual_wallbox(
	*,
	host: str = "127.0.0.1",
	port: int = 15020,
	scenario: Scenario | None = None,
	state: VirtualWallboxState | None = None,
) -> Iterator[VirtualWallboxState]:
	"""Register a virtual wallbox for the duration of the context manager."""

	if state is None:
		if scenario is None:
			scenario = build_default_scenario()
		state = scenario.create_state()
	unit_id = state.unit_id
	registry.register(host, port, unit_id, state)
	try:
		yield state
	finally:
		registry.unregister(host, port, unit_id)


class FakeAsyncModbusTcpClient:
	"""Drop-in replacement for :class:`pymodbus.AsyncModbusTcpClient`."""

	def __init__(self, host: str, *, port: int, timeout: float | None = None) -> None:
		self._host = host
		self._port = port
		self._timeout = timeout
		self._connected = False

	async def connect(self) -> None:
		if not registry.has_endpoint(self._host, self._port):
			raise FakeModbusException(
				f"No virtual wallbox available at {self._host}:{self._port}"
			)
		self._connected = True

	async def close(self) -> None:
		self._connected = False

	@property
	def connected(self) -> bool:
		return self._connected

	async def read_input_registers(self, address: int, count: int, *, unit: int) -> _FakeReadResult:
		state = registry.require(self._host, self._port, unit)
		return _FakeReadResult(state.read_block("input", address, count))

	async def read_holding_registers(
		self,
		address: int,
		count: int,
		*,
		unit: int,
	) -> _FakeReadResult:
		state = registry.require(self._host, self._port, unit)
		return _FakeReadResult(state.read_block("holding", address, count))

	async def write_register(self, address: int, value: int, *, unit: int) -> _FakeWriteResult:
		state = registry.require(self._host, self._port, unit)
		state.write_register(address, value)
		return _FakeWriteResult()


def build_default_scenario(*, unit_id: int = 255) -> Scenario:
	"""Return a baseline scenario that mimics an idle wallbox."""

	return Scenario(
		unit_id=unit_id,
		values={
			"serial_number": "SIM-WB-0001",
			"charge_point_id": "SIMULATOR",
			"charge_point_brand": "Webasto",
			"charge_point_model": "Next",
			"firmware_version": "1.0.0",
			"charge_point_state": 0,
			"charging_state": 0,
			"equipment_state": 1,
			"cable_state": 2,
			"fault_code": 0,
			"current_l1_a": 0,
			"current_l2_a": 0,
			"current_l3_a": 0,
			"voltage_l1_v": 230,
			"voltage_l2_v": 230,
			"voltage_l3_v": 230,
			"active_power_total_w": 0,
			"active_power_l1_w": 0,
			"active_power_l2_w": 0,
			"active_power_l3_w": 0,
			"energy_total_kwh": 1234.567,
			"session_max_current_a": 32,
			"evse_min_current_a": 6,
			"evse_max_current_a": 32,
			"cable_max_current_a": 32,
			"ev_max_current_a": 32,
			"charged_energy_wh": 0,
			"session_start_time": 0,
			"session_duration_s": 0,
			"session_end_time": 0,
			"rated_power_w": 22000,
			"phase_configuration": 1,
			"charge_power_w": 0,
			"failsafe_current_a": 16,
			"failsafe_timeout_s": 60,
		},
		write_actions={
			"session_command": {
				SESSION_COMMAND_START_VALUE: {
					"charging_state": 1,
					"charge_point_state": 2,
					"active_power_total_w": 7400,
					"active_power_l1_w": 2466,
					"active_power_l2_w": 2466,
					"active_power_l3_w": 2466,
					"charge_power_w": 7400,
				},
				SESSION_COMMAND_STOP_VALUE: {
					"charging_state": 0,
					"charge_point_state": 0,
					"active_power_total_w": 0,
					"active_power_l1_w": 0,
					"active_power_l2_w": 0,
					"active_power_l3_w": 0,
					"charge_power_w": 0,
				},
			},
		},
	)


def _encode_value(definition: RegisterDefinition, value: Any) -> list[int]:
	"""Translate a high-level value into raw Modbus register words."""

	if value is None:
		return [0] * definition.count

	if definition.data_type == "string":
		encoding = definition.encoding or "utf-8"
		text = str(value)
		byte_length = definition.count * 2
		data = text.encode(encoding)
		if len(data) > byte_length:
			raise ValueError(
				f"Value '{text}' exceeds capacity of {definition.count} registers for "
				f"{definition.key}"
			)
		padded = data.ljust(byte_length, b"\x00")
		return [int.from_bytes(padded[i : i + 2], "big") for i in range(0, byte_length, 2)]

	scale = definition.scale
	if definition.data_type == "uint16":
		numeric = float(value)
		raw = int(round(numeric / scale)) if scale != 1 else int(round(numeric))
		if not 0 <= raw <= 0xFFFF:
			raise ValueError(f"Value {value} out of range for 16-bit register {definition.key}")
		return [raw]

	if definition.data_type == "uint32":
		numeric = float(value)
		raw = int(round(numeric / scale)) if scale != 1 else int(round(numeric))
		if not 0 <= raw <= 0xFFFFFFFF:
			raise ValueError(f"Value {value} out of range for 32-bit register {definition.key}")
		return [(raw >> 16) & 0xFFFF, raw & 0xFFFF]

	raise ValueError(f"Unsupported data type: {definition.data_type}")
