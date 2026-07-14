"""Constants and register metadata for the Webasto Next Modbus integration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final, Literal

DOMAIN: Final = "webasto_next_modbus"
DEFAULT_PORT: Final = 502
DEFAULT_UNIT_ID: Final = 255
DEFAULT_SCAN_INTERVAL: Final = 10  # seconds
MIN_SCAN_INTERVAL: Final = 2
MAX_SCAN_INTERVAL: Final = 60
MAX_RETRY_ATTEMPTS: Final = 5
RETRY_BACKOFF_SECONDS: Final = 2.0
FAILURE_NOTIFICATION_THRESHOLD: Final = 3
FAILURE_NOTIFICATION_TITLE: Final = "Webasto Next Modbus connection issue"

CONF_UNIT_ID: Final = "unit_id"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_VARIANT: Final = "variant"
CONF_NAME: Final = "name"

# REST API Configuration
CONF_REST_ENABLED: Final = "rest_enabled"
CONF_REST_USERNAME: Final = "rest_username"
CONF_REST_PASSWORD: Final = "rest_password"
DEFAULT_REST_USERNAME: Final = "admin"
REST_SCAN_INTERVAL: Final = 60  # REST API polling interval (seconds)
REST_SETUP_RETRY_INTERVAL: Final = 300  # retry a failed REST connect this often (seconds)

# Webasto / Ampure Unite REST settings (served via the flat
# `/api/configuration-fields/` endpoint; see issue #97). The LED dimming level
# is an enum on the Unite rather than the Next's 0-100 brightness.
UNITE_LED_DIMMING_LEVELS: Final = ("veryLow", "low", "mid", "high", "timeBased")
UNITE_RANDOMISED_DELAY_MAX: Final = 1800  # seconds

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

# Hardware model axis, separate from the power VARIANT above. The Webasto Next
# and the Webasto / Ampure Unite share most register addresses, but the Unite
# exposes its telemetry block (~100-1513) as input registers instead of holding
# registers, with a handful of data-type / scale / enum differences. See the
# get_*_registers() helpers further down.
CONF_MODEL: Final = "model"
MODEL_NEXT: Final = "next"
MODEL_UNITE: Final = "unite"
DEFAULT_MODEL: Final = MODEL_NEXT
MODEL_LABELS: Final = {
    MODEL_NEXT: "Webasto Next",
    MODEL_UNITE: "Webasto / Ampure Unite",
}
MODEL_DISPLAY_NAMES: Final = {
    MODEL_NEXT: "Next",
    MODEL_UNITE: "Unite",
}

DEVICE_NAME: Final = "Webasto Next Wallbox"
KEEPALIVE_TRIGGER_VALUE: Final = 1
SESSION_COMMAND_START_VALUE: Final = 1
SESSION_COMMAND_STOP_VALUE: Final = 2
SIGNAL_REGISTER_WRITTEN: Final = "webasto_next_modbus_register_written"

# Service names (Modbus)
SERVICE_SET_CURRENT: Final = "set_current"
SERVICE_SET_FAILSAFE: Final = "set_failsafe"
SERVICE_SEND_KEEPALIVE: Final = "send_keepalive"
SERVICE_START_SESSION: Final = "start_session"
SERVICE_STOP_SESSION: Final = "stop_session"

# Service names (REST API)
SERVICE_SET_LED_BRIGHTNESS: Final = "set_led_brightness"
SERVICE_SET_FREE_CHARGING: Final = "set_free_charging"
SERVICE_RESTART_WALLBOX: Final = "restart_wallbox"

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
    entity: Literal["sensor", "number", "button", "switch", "diagnostic"]
    scale: float = 1.0
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    entity_category: str | None = None
    options: dict[int, str] | None = None
    writable: bool = False
    write_only: bool = False
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    encoding: str | None = None
    translation_key: str | None = None
    optional: bool = False  # If True, register will be skipped if unsupported


# Enumerations mapped to user friendly strings.
CHARGE_POINT_STATE_MAP: Final = {
    0: "available",
    1: "preparing",
    3: "charging",
    4: "suspended",
    7: "error",
    8: "reserved",
}

# The Webasto / Ampure Unite reports a different (and wider) charge-point-state
# enum than the Next at register 1000.
UNITE_CHARGE_POINT_STATE_MAP: Final = {
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
        options=CHARGE_POINT_STATE_MAP,
        translation_key="charge_point_state",
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
        options=CHARGING_STATE_MAP,
        translation_key="charging_state",
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
        options=EQUIPMENT_STATE_MAP,
        translation_key="equipment_state",
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
        options=CABLE_STATE_MAP,
        translation_key="cable_state",
    ),
    RegisterDefinition(
        key="fault_code",
        name="EVSE Fault Code",
        address=1006,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="sensor",
        device_class="enum",
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
        translation_key="current_l1_a",
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
        translation_key="current_l2_a",
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
        translation_key="current_l3_a",
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
        translation_key="active_power_total_w",
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
        translation_key="active_power_l1_w",
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
        translation_key="active_power_l2_w",
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
        translation_key="active_power_l3_w",
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
        translation_key="energy_total_kwh",
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
        translation_key="session_max_current_a",
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
        translation_key="evse_min_current_a",
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
        translation_key="evse_max_current_a",
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
        translation_key="cable_max_current_a",
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
        translation_key="ev_max_current_a",
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
        state_class="total",
        translation_key="charged_energy_wh",
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
        translation_key="session_start_time",
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
        translation_key="session_duration_s",
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
        translation_key="session_end_time",
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
        encoding="ascii",
        translation_key="session_user_id",
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
        options=SMART_VEHICLE_STATE_MAP,
        optional=True,  # Only available on TQ-DM100
        translation_key="smart_vehicle_detected",
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
        translation_key="failsafe_current_a",
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
        translation_key="failsafe_timeout_s",
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
        translation_key="set_current_a",
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
        writable=True,
        write_only=True,
        translation_key="send_keepalive",
    ),
    RegisterDefinition(
        key="start_session",
        name="Start Charging",
        address=5006,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="button",
        writable=True,
        write_only=True,
        translation_key="start_session",
    ),
    RegisterDefinition(
        key="stop_session",
        name="Stop Charging",
        address=5006,
        count=1,
        register_type="holding",
        data_type="uint16",
        entity="button",
        writable=True,
        write_only=True,
        translation_key="stop_session",
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


# --------------------------------------------------------------------------- #
# Webasto / Ampure Unite register set
#
# Built from the Next definitions above with the differences from the official
# Webasto UNITE Modbus spec (and confirmed against community Modbus packages):
#   * the whole 100-1513 telemetry block is read as *input* registers
#   * `energy_total_kwh` (1036) is reported in units of 0.1 kWh, not Wh
#   * `charged_energy_wh` (1502) is a uint32, not a 16-bit value
#   * `charge_point_state` (1000) uses a different, 9-state enum
#   * `fault_code` (1006) has no documented enum on the Unite (raw code only)
#   * the Next-only registers (session user id 1600, smart-vehicle-detected
#     1620, start/stop-session command 5006) do not exist on the Unite
#   * extra registers exist on the Unite: per-phase voltage (1014/1016/1018),
#     chargepoint power (400), active phase mode (405, the phase-switch
#     register read back). These are marked `optional=True` because they have
#     not been verified on all firmwares.
# --------------------------------------------------------------------------- #

_UNITE_SENSOR_SKIP: Final = frozenset({"session_user_id", "smart_vehicle_detected"})
_UNITE_SENSOR_OVERRIDES: Final[dict[str, dict[str, object]]] = {
    "charge_point_state": {"options": UNITE_CHARGE_POINT_STATE_MAP},
    # The Unite has no documented fault-code enum, so it surfaces the raw
    # numeric code. Drop the "enum" device class so Home Assistant does not
    # validate the value against a (missing) options list.
    "fault_code": {"options": None, "device_class": None},
    "energy_total_kwh": {"scale": 0.1},
    "charged_energy_wh": {"data_type": "uint32", "count": 2},
}


def _build_unite_sensor_registers() -> tuple[RegisterDefinition, ...]:
    regs: list[RegisterDefinition] = []
    for register in SENSOR_REGISTERS:
        if register.key in _UNITE_SENSOR_SKIP:
            continue
        changes: dict[str, object] = {"register_type": "input"}
        changes.update(_UNITE_SENSOR_OVERRIDES.get(register.key, {}))
        regs.append(replace(register, **changes))  # type: ignore[arg-type]
    regs.extend(
        (
            RegisterDefinition(
                key="voltage_l1",
                name="Voltage L1",
                address=1014,
                count=1,
                register_type="input",
                data_type="uint16",
                entity="sensor",
                unit="V",
                device_class="voltage",
                state_class="measurement",
                optional=True,
                translation_key="voltage_l1",
            ),
            RegisterDefinition(
                key="voltage_l2",
                name="Voltage L2",
                address=1016,
                count=1,
                register_type="input",
                data_type="uint16",
                entity="sensor",
                unit="V",
                device_class="voltage",
                state_class="measurement",
                optional=True,
                translation_key="voltage_l2",
            ),
            RegisterDefinition(
                key="voltage_l3",
                name="Voltage L3",
                address=1018,
                count=1,
                register_type="input",
                data_type="uint16",
                entity="sensor",
                unit="V",
                device_class="voltage",
                state_class="measurement",
                optional=True,
                translation_key="voltage_l3",
            ),
            RegisterDefinition(
                key="chargepoint_power_w",
                name="Chargepoint Power",
                address=400,
                count=2,
                register_type="input",
                data_type="uint32",
                entity="sensor",
                unit="W",
                device_class="power",
                state_class="measurement",
                entity_category="diagnostic",
                optional=True,
                translation_key="chargepoint_power_w",
            ),
            RegisterDefinition(
                key="number_of_phases",
                name="Number of Phases",
                # The active phase mode is the phase-switch holding register
                # (405): 0 = single-phase, 1 = three-phase. Register 404 (input)
                # reports the installed phase count, which stays at 3 on a
                # three-phase install and so doesn't track the active mode.
                address=405,
                count=1,
                register_type="holding",
                data_type="uint16",
                entity="sensor",
                device_class="enum",
                entity_category="diagnostic",
                options=PHASE_COUNT_MAP,
                optional=True,
                translation_key="number_of_phases",
            ),
        )
    )
    return tuple(regs)


UNITE_SENSOR_REGISTERS: Final[tuple[RegisterDefinition, ...]] = _build_unite_sensor_registers()

# Failsafe (2000/2002) and the charging-current limit (5004) are holding
# registers on the Unite too, so the number entities are unchanged.
UNITE_NUMBER_REGISTERS: Final[tuple[RegisterDefinition, ...]] = NUMBER_REGISTERS

# Only the keep-alive register (6000) exists on the Unite; the start/stop
# session command (5006) does not.
UNITE_BUTTON_REGISTERS: Final[tuple[RegisterDefinition, ...]] = tuple(
    register for register in BUTTON_REGISTERS if register.key == "send_keepalive"
)

UNITE_CONTROL_REGISTERS: Final[tuple[RegisterDefinition, ...]] = ()

# Phase switching (1 <-> 3 phase) via holding register 405. Undocumented in the
# v1.00 Modbus spec but confirmed working on Unite FW 3.187 (community reports
# in issue #37). Write value 1 = three-phase, 0 = single-phase; the active phase
# count is read back from `number_of_phases` (404). Marked optional so it is
# harmless on firmwares that don't implement it.
UNITE_PHASE_SWITCH_REGISTER: Final = RegisterDefinition(
    key="phase_switch",
    name="Phase Switch",
    address=405,
    count=1,
    register_type="holding",
    data_type="uint16",
    entity="switch",
    entity_category="config",
    writable=True,
    write_only=True,
    optional=True,
    translation_key="phase_switch",
)

# Next has no register-backed switch; the Unite gets the phase switch.
SWITCH_REGISTERS: Final[tuple[RegisterDefinition, ...]] = ()
UNITE_SWITCH_REGISTERS: Final[tuple[RegisterDefinition, ...]] = (UNITE_PHASE_SWITCH_REGISTER,)


_SENSOR_REGISTERS_BY_MODEL: Final[dict[str, tuple[RegisterDefinition, ...]]] = {
    MODEL_NEXT: SENSOR_REGISTERS,
    MODEL_UNITE: UNITE_SENSOR_REGISTERS,
}
_NUMBER_REGISTERS_BY_MODEL: Final[dict[str, tuple[RegisterDefinition, ...]]] = {
    MODEL_NEXT: NUMBER_REGISTERS,
    MODEL_UNITE: UNITE_NUMBER_REGISTERS,
}
_BUTTON_REGISTERS_BY_MODEL: Final[dict[str, tuple[RegisterDefinition, ...]]] = {
    MODEL_NEXT: BUTTON_REGISTERS,
    MODEL_UNITE: UNITE_BUTTON_REGISTERS,
}
_CONTROL_REGISTERS_BY_MODEL: Final[dict[str, tuple[RegisterDefinition, ...]]] = {
    MODEL_NEXT: CONTROL_REGISTERS,
    MODEL_UNITE: UNITE_CONTROL_REGISTERS,
}
_SWITCH_REGISTERS_BY_MODEL: Final[dict[str, tuple[RegisterDefinition, ...]]] = {
    MODEL_NEXT: SWITCH_REGISTERS,
    MODEL_UNITE: UNITE_SWITCH_REGISTERS,
}


def normalize_model(model: str | None) -> str:
    """Return a known model identifier, falling back to the default."""

    return model if model in _SENSOR_REGISTERS_BY_MODEL else DEFAULT_MODEL


def get_model_display_name(model: str | None = None) -> str:
    """Return the human-readable model name (used for the device registry)."""

    return MODEL_DISPLAY_NAMES[normalize_model(model)]


def get_sensor_registers(model: str | None = None) -> tuple[RegisterDefinition, ...]:
    """Return the sensor register definitions for the given model."""

    return _SENSOR_REGISTERS_BY_MODEL[normalize_model(model)]


def get_number_registers(model: str | None = None) -> tuple[RegisterDefinition, ...]:
    """Return the number register definitions for the given model."""

    return _NUMBER_REGISTERS_BY_MODEL[normalize_model(model)]


def get_button_registers(model: str | None = None) -> tuple[RegisterDefinition, ...]:
    """Return the button register definitions for the given model."""

    return _BUTTON_REGISTERS_BY_MODEL[normalize_model(model)]


def get_switch_registers(model: str | None = None) -> tuple[RegisterDefinition, ...]:
    """Return the Modbus switch register definitions for the given model."""

    return _SWITCH_REGISTERS_BY_MODEL[normalize_model(model)]


def get_control_registers(model: str | None = None) -> tuple[RegisterDefinition, ...]:
    """Return the write-only control register definitions for the given model."""

    return _CONTROL_REGISTERS_BY_MODEL[normalize_model(model)]


def get_readable_registers(
    model: str | None = None, include_write_only: bool = False
) -> tuple[RegisterDefinition, ...]:
    """Return every register that should be polled for the given model."""

    model = normalize_model(model)
    regs: list[RegisterDefinition] = list(_SENSOR_REGISTERS_BY_MODEL[model])
    for register in _NUMBER_REGISTERS_BY_MODEL[model]:
        if include_write_only or not register.write_only:
            regs.append(register)
    return tuple(regs)


def all_registers(include_write_only: bool = False) -> tuple[RegisterDefinition, ...]:
    """Return the Webasto Next readable registers (kept for backwards compat)."""

    return get_readable_registers(MODEL_NEXT, include_write_only)


def get_register(key: str) -> RegisterDefinition:
    """Retrieve a register definition by key across all supported models."""

    seen: set[int] = set()
    for collection in (
        *_SENSOR_REGISTERS_BY_MODEL.values(),
        *_NUMBER_REGISTERS_BY_MODEL.values(),
        *_BUTTON_REGISTERS_BY_MODEL.values(),
        *_CONTROL_REGISTERS_BY_MODEL.values(),
        *_SWITCH_REGISTERS_BY_MODEL.values(),
    ):
        if id(collection) in seen:
            continue
        seen.add(id(collection))
        for register in collection:
            if register.key == key:
                return register
    raise KeyError(key)


def build_device_slug(host: str, unit_id: int) -> str:
    """Return the canonical device slug used for device registry identifiers."""

    return f"{host.lower()}-{unit_id}"


def get_max_current_for_variant(variant: str | None) -> int:
    """Return the maximum supported current for the configured variant."""

    if variant in VARIANT_MAX_CURRENT:
        return VARIANT_MAX_CURRENT[variant]
    return VARIANT_MAX_CURRENT[DEFAULT_VARIANT]
