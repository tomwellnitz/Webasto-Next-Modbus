"""Constants and register metadata for the Webasto Next Modbus integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

DOMAIN: Final = "webasto_next_modbus"
INTEGRATION_VERSION: Final = "0.4.0-beta.10"
DEFAULT_PORT: Final = 502
DEFAULT_UNIT_ID: Final = 255
DEFAULT_SCAN_INTERVAL: Final = 10  # seconds
MIN_SCAN_INTERVAL: Final = 2
MAX_SCAN_INTERVAL: Final = 60
MAX_RETRY_ATTEMPTS: Final = 3
RETRY_BACKOFF_SECONDS: Final = 1.0
FAILURE_NOTIFICATION_THRESHOLD: Final = 3
FAILURE_NOTIFICATION_TITLE: Final = "Webasto Next Modbus connection issue"

CONF_UNIT_ID: Final = "unit_id"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_VARIANT: Final = "variant"
CONF_NAME: Final = "name"

VARIANT_11_KW: Final = "11kw"
VARIANT_22_KW: Final = "22kw"
DEFAULT_VARIANT: Final = VARIANT_22_KW

VARIANT_LABELS: Final = {
    VARIANT_11_KW: "11 kW (16 A)",
    VARIANT_22_KW: "22 kW (32 A)",
}

VARIANT_MAX_CURRENT: Final = {
    VARIANT_11_KW: 16,
    VARIANT_22_KW: 32,
}

MANUFACTURER: Final = "Webasto"
MODEL: Final = "Next"
DEVICE_NAME: Final = "Webasto Next Wallbox"
KEEPALIVE_TRIGGER_VALUE: Final = 1
SESSION_COMMAND_START_VALUE: Final = 1
SESSION_COMMAND_STOP_VALUE: Final = 2
SIGNAL_REGISTER_WRITTEN: Final = "webasto_next_modbus_register_written"

REGISTER_TYPE = Literal["input", "holding"]
REGISTER_DATA_TYPE = Literal["uint16", "uint32", "string"]


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
    encoding: str | None = None
    translation_key: str | None = None


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
    0: "starting",
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

PHASE_COUNT_MAP: Final = {
    0: "single_phase",
    1: "three_phase",
}

SMART_VEHICLE_STATE_MAP: Final = {
    0: "not_detected",
    1: "detected",
}

FAULT_CODE_MAP: Final = {
    0: "ok",
    1: "power_switch_failure",
    2: "internal_error_aux_voltage",
    3: "ev_communication_error_control_pilot",
    4: "over_voltage",
    5: "under_voltage",
    6: "over_current_failure",
    7: "vac_frequency_error",
    8: "ground_failure",
    9: "rcm_self_test_error",
    10: "over_temperature",
    11: "proximity_pilot_error",
    12: "shutter_error",
    13: "phase_check_error",
    14: "pwr_internal_error",
    15: "ev_communication_error_negative_pilot",
    16: "dc_residual_current_error",
}


SENSOR_REGISTERS: Final[tuple[RegisterDefinition, ...]] = (
    RegisterDefinition(
        key="charge_point_state",
        name="Charge Point State",
        address=1000,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="sensor",
        device_class="enum",
        icon="mdi:ev-station",
        options=CHARGE_POINT_STATE_MAP,
    ),
    RegisterDefinition(
        key="charging_state",
        name="Charging State",
        address=1001,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="sensor",
        device_class="enum",
        icon="mdi:battery-charging",
        options=CHARGING_STATE_MAP,
    ),
    RegisterDefinition(
        key="equipment_state",
        name="EVSE State",
        address=1002,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="sensor",
        device_class="enum",
        icon="mdi:cog-outline",
        options=EQUIPMENT_STATE_MAP,
    ),
    RegisterDefinition(
        key="cable_state",
        name="Cable State",
        address=1004,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="sensor",
        device_class="enum",
        icon="mdi:cable-data",
        options=CABLE_STATE_MAP,
    ),
    RegisterDefinition(
        key="fault_code",
        name="EVSE Fault Code",
        address=1006,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="sensor",
        icon="mdi:alert",
        entity_category="diagnostic",
        options=FAULT_CODE_MAP,
        translation_key="fault_code",
    ),
    RegisterDefinition(
        key="current_l1_a",
        name="Current L1",
        address=1008,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="sensor",
        scale=0.001,
        unit="A",
        device_class="current",
        state_class="measurement",
        icon="mdi:current-ac",
    ),
    RegisterDefinition(
        key="current_l2_a",
        name="Current L2",
        address=1010,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="sensor",
        scale=0.001,
        unit="A",
        device_class="current",
        state_class="measurement",
        icon="mdi:current-ac",
    ),
    RegisterDefinition(
        key="current_l3_a",
        name="Current L3",
        address=1012,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="sensor",
        scale=0.001,
        unit="A",
        device_class="current",
        state_class="measurement",
        icon="mdi:current-ac",
    ),
    RegisterDefinition(
        key="active_power_total_w",
        name="Active Power Total",
        address=1020,
        count=2,
        register_type="holding",
        data_type="uint32",
        entity="sensor",
        unit="W",
        device_class="power",
        state_class="measurement",
        icon="mdi:lightning-bolt",
    ),
    RegisterDefinition(
        key="active_power_l1_w",
        name="Active Power L1",
        address=1024,
        count=2,
        register_type="holding",
        data_type="uint32",
        entity="sensor",
        unit="W",
        device_class="power",
        state_class="measurement",
        icon="mdi:lightning-bolt",
    ),
    RegisterDefinition(
        key="active_power_l2_w",
        name="Active Power L2",
        address=1028,
        count=2,
        register_type="holding",
        data_type="uint32",
        entity="sensor",
        unit="W",
        device_class="power",
        state_class="measurement",
        icon="mdi:lightning-bolt",
    ),
    RegisterDefinition(
        key="active_power_l3_w",
        name="Active Power L3",
        address=1032,
        count=2,
        register_type="holding",
        data_type="uint32",
        entity="sensor",
        unit="W",
        device_class="power",
        state_class="measurement",
        icon="mdi:lightning-bolt",
    ),
    RegisterDefinition(
        key="energy_total_kwh",
        name="Energy Total",
        address=1036,
        count=2,
        register_type="holding",
        data_type="uint32",
        entity="sensor",
        scale=0.001,
        unit="kWh",
        device_class="energy",
        state_class="total_increasing",
        icon="mdi:counter",
    ),
    RegisterDefinition(
        key="session_max_current_a",
        name="Max Current",
        address=1100,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="sensor",
        unit="A",
        device_class="current",
        state_class="measurement",
        entity_category="diagnostic",
        icon="mdi:current-ac",
    ),
    RegisterDefinition(
        key="evse_min_current_a",
        name="EVSE Min Current",
        address=1102,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="sensor",
        unit="A",
        device_class="current",
        entity_category="diagnostic",
        icon="mdi:current-ac",
    ),
    RegisterDefinition(
        key="evse_max_current_a",
        name="EVSE Max Current",
        address=1104,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="sensor",
        unit="A",
        device_class="current",
        entity_category="diagnostic",
        icon="mdi:current-ac",
    ),
    RegisterDefinition(
        key="cable_max_current_a",
        name="Cable Max Current",
        address=1106,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="sensor",
        unit="A",
        device_class="current",
        entity_category="diagnostic",
        icon="mdi:current-ac",
    ),
    RegisterDefinition(
        key="ev_max_current_a",
        name="EV Max Current",
        address=1108,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="sensor",
        unit="A",
        device_class="current",
        entity_category="diagnostic",
        icon="mdi:current-ac",
    ),
    RegisterDefinition(
        key="charged_energy_wh",
        name="Charged Energy",
        address=1502,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="sensor",
        unit="Wh",
        device_class="energy",
        state_class="measurement",
        icon="mdi:battery-clock",
    ),
    RegisterDefinition(
        key="session_start_time",
        name="Start Time (hhmmss)",
        address=1504,
        count=2,
        register_type="holding",
        data_type="uint32",
        entity="sensor",
        entity_category="diagnostic",
        icon="mdi:clock-start",
    ),
    RegisterDefinition(
        key="session_duration_s",
        name="Charging Time",
        address=1508,
        count=2,
        register_type="holding",
        data_type="uint32",
        entity="sensor",
        unit="s",
        device_class="duration",
        state_class="measurement",
        entity_category="diagnostic",
        icon="mdi:timer-outline",
    ),
    RegisterDefinition(
        key="session_end_time",
        name="End Time (hhmmss)",
        address=1512,
        count=2,
        register_type="holding",
        data_type="uint32",
        entity="sensor",
        entity_category="diagnostic",
        icon="mdi:clock-end",
    ),
    RegisterDefinition(
        key="session_user_id",
        name="User ID",
        address=1600,
        count=10,
        register_type="holding",
        data_type="string",
        entity="sensor",
        entity_category="diagnostic",
        icon="mdi:card-account-details",
        encoding="ascii",
    ),
    RegisterDefinition(
        key="smart_vehicle_detected",
        name="Smart Vehicle Detected",
        address=1620,
        count=2,
        register_type="holding",
        data_type="uint32",
        entity="sensor",
        device_class="enum",
        entity_category="diagnostic",
        icon="mdi:car-connected",
        options=SMART_VEHICLE_STATE_MAP,
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
        icon="mdi:current-ac",
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
        icon="mdi:timer-outline",
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
        icon="mdi:speedometer",
        writable=True,
        write_only=True,
        min_value=0,
        max_value=32,
        step=1,
    ),
)


BUTTON_REGISTERS: Final[tuple[RegisterDefinition, ...]] = (
    # IMPORTANT: Register 6000 (Life Bit) MUST be written every 20s.
    # Required for custom Modbus implementations to avoid timeouts.
    RegisterDefinition(
        key="send_keepalive",
        name="Send Keepalive",
        address=6000,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="button",
        icon="mdi:lan-connect",
        writable=True,
        write_only=True,
    ),
    RegisterDefinition(
        key="start_session",
        name="Start Charging",
        address=5006,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="button",
        icon="mdi:play",
        writable=True,
        write_only=True,
    ),
    RegisterDefinition(
        key="stop_session",
        name="Stop Charging",
        address=5006,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="button",
        icon="mdi:stop-circle",
        writable=True,
        write_only=True,
    ),
)


CONTROL_REGISTERS: Final[tuple[RegisterDefinition, ...]] = (
    RegisterDefinition(
        key="session_command",
        name="Session Command",
        address=5006,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="diagnostic",
        writable=True,
        write_only=True,
        entity_category="diagnostic",
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

    for register in (*SENSOR_REGISTERS, *NUMBER_REGISTERS, *BUTTON_REGISTERS, *CONTROL_REGISTERS):
        if register.key == key:
            return register
    raise KeyError(key)


SERVICE_SET_CURRENT: Final = "set_current"
SERVICE_SET_FAILSAFE: Final = "set_failsafe"
SERVICE_SEND_KEEPALIVE: Final = "send_keepalive"
SERVICE_START_SESSION: Final = "start_session"
SERVICE_STOP_SESSION: Final = "stop_session"


def build_device_slug(host: str, unit_id: int) -> str:
    """Return the canonical device slug used for device registry identifiers."""

    return f"{host.lower()}-{unit_id}"


def get_max_current_for_variant(variant: str | None) -> int:
    """Return the maximum supported current for the configured variant."""

    if variant in VARIANT_MAX_CURRENT:
        return VARIANT_MAX_CURRENT[variant]
    return VARIANT_MAX_CURRENT[DEFAULT_VARIANT]
