"""Static checks on the register and REST sensor definitions.

The entity constructors ignore enum strings they cannot parse (so a bad value
never breaks setup); these tests make sure that never actually happens.
"""

from __future__ import annotations

from enum import StrEnum

import pytest
from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory

from custom_components.webasto_next_modbus import const
from custom_components.webasto_next_modbus.sensor import REST_SENSORS, RestSensorDefinition

ALL_REGISTERS: tuple[const.RegisterDefinition, ...] = (
    *const.SENSOR_REGISTERS,
    *const.NUMBER_REGISTERS,
    *const.BUTTON_REGISTERS,
    *const.CONTROL_REGISTERS,
    *const.UNITE_SENSOR_REGISTERS,
    *const.UNITE_SWITCH_REGISTERS,
)


def _assert_member(enum: type[StrEnum], value: str | None) -> None:
    if value is not None:
        assert value in {member.value for member in enum}, f"{value!r} is not a {enum.__name__}"


@pytest.mark.parametrize("register", ALL_REGISTERS, ids=lambda r: r.key)
def test_register_enum_strings_are_valid(register: const.RegisterDefinition) -> None:
    _assert_member(EntityCategory, register.entity_category)
    if register.entity == "number":
        _assert_member(NumberDeviceClass, register.device_class)
    elif register.entity in ("sensor", "diagnostic"):
        _assert_member(SensorDeviceClass, register.device_class)
        _assert_member(SensorStateClass, register.state_class)


@pytest.mark.parametrize("definition", REST_SENSORS, ids=lambda d: d.key)
def test_rest_sensor_enum_strings_are_valid(definition: RestSensorDefinition) -> None:
    _assert_member(EntityCategory, definition.entity_category)
    _assert_member(SensorDeviceClass, definition.device_class)
    _assert_member(SensorStateClass, definition.state_class)


def test_register_keys_are_unique_per_model() -> None:
    for model in (const.MODEL_NEXT, const.MODEL_UNITE):
        keys = [
            register.key
            for register in (
                *const.get_sensor_registers(model),
                *const.get_number_registers(model),
                *const.get_button_registers(model),
                *const.get_switch_registers(model),
            )
        ]
        assert len(keys) == len(set(keys)), model
