"""Constants and register metadata for the Webasto Next Modbus integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

DOMAIN: Final = "webasto_next_modbus"
INTEGRATION_VERSION: Final = "0.1.0"
DEFAULT_PORT: Final = 502
DEFAULT_UNIT_ID: Final = 255
DEFAULT_SCAN_INTERVAL: Final = 5  # seconds
MIN_SCAN_INTERVAL: Final = 2
MAX_SCAN_INTERVAL: Final = 60

CONF_UNIT_ID: Final = "unit_id"
CONF_SCAN_INTERVAL: Final = "scan_interval"

MANUFACTURER: Final = "Webasto"
MODEL: Final = "Next"
DEVICE_NAME: Final = "Webasto Next Wallbox"
KEEPALIVE_TRIGGER_VALUE: Final = 1

REGISTER_TYPE = Literal["input", "holding"]
REGISTER_DATA_TYPE = Literal["uint16", "uint32"]


@dataclass(frozen=True, slots=True)
class RegisterDefinition:
	"""Describe a Modbus register that should be exposed to Home Assistant."""

	key: str
	name: str
	address: int
	count: int
	register_type: REGISTER_TYPE
	data_type: REGISTER_DATA_TYPE
	entity: Literal["sensor", "number", "button", "diagnostic"]
	scale: float = 1.0
	unit: str | None = None
	device_class: str | None = None
	state_class: str | None = None
	icon: str | None = None
	entity_category: str | None = None
	options: dict[int, str] | None = None
	writable: bool = False
	write_only: bool = False
	min_value: float | None = None
	max_value: float | None = None
	step: float | None = None


# Enumerations mapped to user friendly strings.
CHARGE_POINT_STATE_MAP: Final = {
	0: "available",
	1: "preparing",
	2: "charging",
	3: "suspended_evse",
	4: "suspended_ev",
	5: "finishing",
	6: "reserved",
	7: "unavailable",
	8: "faulted",
}

CHARGING_STATE_MAP: Final = {
	0: "idle",
	1: "charging",
}

EQUIPMENT_STATE_MAP: Final = {
	0: "initializing",
	1: "running",
	2: "fault",
	3: "disabled",
	4: "updating",
}

CABLE_STATE_MAP: Final = {
	0: "disconnected",
	1: "cable_only",
	2: "vehicle_connected",
	3: "vehicle_locked",
}


SENSOR_REGISTERS: Final[tuple[RegisterDefinition, ...]] = (
	RegisterDefinition(
		key="charge_point_state",
		name="Charge Point State",
		address=1000,
		count=1,
		register_type="input",
		data_type="uint16",
		entity="sensor",
		device_class="enum",
		options=CHARGE_POINT_STATE_MAP,
	),
	RegisterDefinition(
		key="charging_state",
		name="Charging State",
		address=1001,
		count=1,
		register_type="input",
		data_type="uint16",
		entity="sensor",
		device_class="enum",
		options=CHARGING_STATE_MAP,
	),
	RegisterDefinition(
		key="equipment_state",
		name="Equipment State",
		address=1002,
		count=1,
		register_type="input",
		data_type="uint16",
		entity="sensor",
		device_class="enum",
		options=EQUIPMENT_STATE_MAP,
	),
	RegisterDefinition(
		key="cable_state",
		name="Cable State",
		address=1004,
		count=1,
		register_type="input",
		data_type="uint16",
		entity="sensor",
		device_class="enum",
		options=CABLE_STATE_MAP,
	),
	RegisterDefinition(
		key="fault_code",
		name="EVSE Fault Code",
		address=1006,
		count=1,
		register_type="input",
		data_type="uint16",
		entity="sensor",
		icon="mdi:alert",
		entity_category="diagnostic",
	),
	RegisterDefinition(
		key="current_l1_a",
		name="Current L1",
		address=1008,
		count=1,
		register_type="input",
		data_type="uint16",
		entity="sensor",
		scale=0.001,
		unit="A",
		device_class="current",
		state_class="measurement",
	),
	RegisterDefinition(
		key="current_l2_a",
		name="Current L2",
		address=1010,
		count=1,
		register_type="input",
		data_type="uint16",
		entity="sensor",
		scale=0.001,
		unit="A",
		device_class="current",
		state_class="measurement",
	),
	RegisterDefinition(
		key="current_l3_a",
		name="Current L3",
		address=1012,
		count=1,
		register_type="input",
		data_type="uint16",
		entity="sensor",
		scale=0.001,
		unit="A",
		device_class="current",
		state_class="measurement",
	),
	RegisterDefinition(
		key="voltage_l1_v",
		name="Voltage L1",
		address=1014,
		count=1,
		register_type="input",
		data_type="uint16",
		entity="sensor",
		unit="V",
		device_class="voltage",
		state_class="measurement",
	),
	RegisterDefinition(
		key="voltage_l2_v",
		name="Voltage L2",
		address=1016,
		count=1,
		register_type="input",
		data_type="uint16",
		entity="sensor",
		unit="V",
		device_class="voltage",
		state_class="measurement",
	),
	RegisterDefinition(
		key="voltage_l3_v",
		name="Voltage L3",
		address=1018,
		count=1,
		register_type="input",
		data_type="uint16",
		entity="sensor",
		unit="V",
		device_class="voltage",
		state_class="measurement",
	),
	RegisterDefinition(
		key="active_power_total_w",
		name="Active Power Total",
		address=1020,
		count=2,
		register_type="input",
		data_type="uint32",
		entity="sensor",
		unit="W",
		device_class="power",
		state_class="measurement",
	),
	RegisterDefinition(
		key="active_power_l1_w",
		name="Active Power L1",
		address=1024,
		count=2,
		register_type="input",
		data_type="uint32",
		entity="sensor",
		unit="W",
		device_class="power",
		state_class="measurement",
	),
	RegisterDefinition(
		key="active_power_l2_w",
		name="Active Power L2",
		address=1028,
		count=2,
		register_type="input",
		data_type="uint32",
		entity="sensor",
		unit="W",
		device_class="power",
		state_class="measurement",
	),
	RegisterDefinition(
		key="active_power_l3_w",
		name="Active Power L3",
		address=1032,
		count=2,
		register_type="input",
		data_type="uint32",
		entity="sensor",
		unit="W",
		device_class="power",
		state_class="measurement",
	),
	RegisterDefinition(
		key="energy_total_kwh",
		name="Energy Total",
		address=1036,
		count=2,
		register_type="input",
		data_type="uint32",
		entity="sensor",
		scale=0.001,
		unit="kWh",
		device_class="energy",
		state_class="total_increasing",
	),
	RegisterDefinition(
		key="session_max_current_a",
		name="Session Max Current",
		address=1100,
		count=1,
		register_type="input",
		data_type="uint16",
		entity="sensor",
		unit="A",
		device_class="current",
		state_class="measurement",
		entity_category="diagnostic",
	),
	RegisterDefinition(
		key="evse_min_current_a",
		name="EVSE Min Current",
		address=1102,
		count=1,
		register_type="input",
		data_type="uint16",
		entity="sensor",
		unit="A",
		device_class="current",
		entity_category="diagnostic",
	),
	RegisterDefinition(
		key="evse_max_current_a",
		name="EVSE Max Current",
		address=1104,
		count=1,
		register_type="input",
		data_type="uint16",
		entity="sensor",
		unit="A",
		device_class="current",
		entity_category="diagnostic",
	),
	RegisterDefinition(
		key="cable_max_current_a",
		name="Cable Max Current",
		address=1106,
		count=1,
		register_type="input",
		data_type="uint16",
		entity="sensor",
		unit="A",
		device_class="current",
		entity_category="diagnostic",
	),
	RegisterDefinition(
		key="session_start_time",
		name="Session Start Time",
		address=1504,
		count=2,
		register_type="input",
		data_type="uint32",
		entity="sensor",
		entity_category="diagnostic",
		icon="mdi:clock-start",
	),
	RegisterDefinition(
		key="session_duration_s",
		name="Session Duration",
		address=1508,
		count=2,
		register_type="input",
		data_type="uint32",
		entity="sensor",
		unit="s",
		device_class="duration",
		state_class="measurement",
		entity_category="diagnostic",
	),
	RegisterDefinition(
		key="session_end_time",
		name="Session End Time",
		address=1512,
		count=2,
		register_type="input",
		data_type="uint32",
		entity="sensor",
		entity_category="diagnostic",
		icon="mdi:clock-end",
	),
)


NUMBER_REGISTERS: Final[tuple[RegisterDefinition, ...]] = (
	RegisterDefinition(
		key="failsafe_current_a",
		name="Failsafe Current",
		address=2000,
		count=1,
		register_type="holding",
		data_type="uint16",
		entity="number",
		unit="A",
		device_class="current",
		writable=True,
		min_value=6,
		max_value=32,
		step=1,
	),
	RegisterDefinition(
		key="failsafe_timeout_s",
		name="Failsafe Timeout",
		address=2002,
		count=1,
		register_type="holding",
		data_type="uint16",
		entity="number",
		unit="s",
		writable=True,
		min_value=6,
		max_value=120,
		step=1,
	),
	RegisterDefinition(
		key="set_current_a",
		name="Charging Current Limit",
		address=5004,
		count=1,
		register_type="holding",
		data_type="uint16",
		entity="number",
		unit="A",
		device_class="current",
		writable=True,
		write_only=True,
		min_value=0,
		max_value=32,
		step=1,
	),
)


BUTTON_REGISTERS: Final[tuple[RegisterDefinition, ...]] = (
	RegisterDefinition(
		key="send_keepalive",
		name="Send Keepalive",
		address=6000,
		count=1,
		register_type="holding",
		data_type="uint16",
		entity="button",
		writable=True,
		write_only=True,
	),
)


def all_registers(include_write_only: bool = False) -> tuple[RegisterDefinition, ...]:
	"""Return all register definitions, optionally including write-only ones."""

	regs: list[RegisterDefinition] = []
	regs.extend(SENSOR_REGISTERS)
	for register in NUMBER_REGISTERS:
		if include_write_only or not register.write_only:
			regs.append(register)
	return tuple(regs)


def get_register(key: str) -> RegisterDefinition:
	"""Retrieve a register definition by key."""

	for register in (*SENSOR_REGISTERS, *NUMBER_REGISTERS, *BUTTON_REGISTERS):
		if register.key == key:
			return register
	raise KeyError(key)


SERVICE_SET_CURRENT: Final = "set_current"
SERVICE_SET_FAILSAFE: Final = "set_failsafe"
SERVICE_SEND_KEEPALIVE: Final = "send_keepalive"
