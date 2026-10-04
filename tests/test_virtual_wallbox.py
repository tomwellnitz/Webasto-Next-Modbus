"""Integration style tests using the virtual wallbox simulator."""

from __future__ import annotations

import pytest

from custom_components.webasto_next_modbus.const import SESSION_COMMAND_START_VALUE, get_register
from custom_components.webasto_next_modbus.hub import ModbusBridge
from virtual_wallbox.server import VirtualWallboxDataBlock, VirtualWallboxDeviceContext
from virtual_wallbox.simulator import (
    Scenario,
    VirtualWallboxUnit,
    build_default_scenario,
    register_virtual_wallbox,
)


def _make_bridge(host: str, port: int, unit_id: int, **kwargs: object) -> ModbusBridge:
    """Create a Modbus bridge on an in-process unit of the virtual wallbox."""

    return ModbusBridge(
        VirtualWallboxUnit(host, port, unit_id),
        host=host,
        port=port,
        unit_id=unit_id,
        **kwargs,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_bridge_reads_data_from_virtual_wallbox(default_virtual_wallbox) -> None:
    """The Modbus bridge should decode values provided by the simulator."""

    host = "127.0.0.1"
    port = 15020
    unit = default_virtual_wallbox.unit_id

    bridge = _make_bridge(host, port, unit)
    data = await bridge.async_read_data()

    assert data["charging_state"] == 0
    assert data["active_power_total_w"] == 0


@pytest.mark.asyncio
async def test_bridge_write_actions_update_simulated_state() -> None:
    """Writing the session command should flip charging related registers."""

    scenario = build_default_scenario()
    host = "192.0.2.1"
    port = 5020

    with register_virtual_wallbox(host=host, port=port, scenario=scenario) as state:
        bridge = _make_bridge(host, port, state.unit_id)
        await bridge.async_write_register(get_register("session_command"), 1)
        data = await bridge.async_read_data()
        assert data["charging_state"] == 1
        assert data["charge_point_state"] == 3

        await bridge.async_write_register(get_register("session_command"), 2)
        data_after_stop = await bridge.async_read_data()
        assert data_after_stop["charging_state"] == 0
        assert data_after_stop["charge_point_state"] == 0


@pytest.mark.asyncio
async def test_custom_scenario_values_are_exposed() -> None:
    """Scenarios may override any register exposed through the bridge."""

    sim = Scenario(
        values={
            "charging_state": 1,
            "active_power_total_w": 11800,
        },
    )
    host = "198.51.100.44"
    port = 18000

    with register_virtual_wallbox(host=host, port=port, scenario=sim) as state:
        bridge = _make_bridge(host, port, state.unit_id)
        payload = await bridge.async_read_data()

    assert payload["active_power_total_w"] == 11800
    assert payload["charging_state"] == 1


@pytest.mark.asyncio
async def test_unite_serves_telemetry_only_as_input_registers() -> None:
    """A virtual Unite exposes telemetry on input registers, not holding."""

    from custom_components.webasto_next_modbus.const import (
        MODEL_NEXT,
        MODEL_UNITE,
        UNITE_PHASE_SWITCH_REGISTER,
        get_readable_registers,
    )

    scenario = Scenario(
        model=MODEL_UNITE,
        values={
            "charge_point_state": 2,
            "voltage_l1": 232,
            "energy_total_kwh": 39.9,
            "number_of_phases": 1,
        },
    )
    host = "198.51.100.70"
    port = 15099

    with register_virtual_wallbox(host=host, port=port, scenario=scenario) as state:
        unite_bridge = _make_bridge(
            host, port, state.unit_id, registers=get_readable_registers(MODEL_UNITE)
        )
        unite_data = await unite_bridge.async_read_data()

        # The Unite reads its telemetry as input registers and decodes correctly.
        assert unite_data["charge_point_state"] == 2
        assert unite_data["voltage_l1"] == 232
        assert unite_data["energy_total_kwh"] == pytest.approx(39.9)

        # Reading the same wallbox with the Next (holding) map yields nothing,
        # which is exactly the "all sensors read 0 on a Unite" failure.
        next_bridge = _make_bridge(
            host, port, state.unit_id, registers=get_readable_registers(MODEL_NEXT)
        )
        next_data = await next_bridge.async_read_data()
        assert next_data["charge_point_state"] == 0

        # The phase switch (holding 405) round-trips into number_of_phases.
        await unite_bridge.async_write_register(UNITE_PHASE_SWITCH_REGISTER, 0)
        assert (await unite_bridge.async_read_data())["number_of_phases"] == 0
        await unite_bridge.async_write_register(UNITE_PHASE_SWITCH_REGISTER, 1)
        assert (await unite_bridge.async_read_data())["number_of_phases"] == 1


def test_data_block_resolves_one_based_addresses() -> None:
    """Data block should map 0-based addresses produced by Modbus contexts."""

    scenario = build_default_scenario()
    state = scenario.create_state()
    state.apply_values({"charging_state": 1})
    block = VirtualWallboxDataBlock(state, "input", zero_mode=False)

    assert block.getValues(1000, 1) == [1]


def test_data_block_write_triggers_actions() -> None:
    """Writing a holding register through the data block should apply actions."""

    scenario = build_default_scenario()
    state = scenario.create_state()
    block = VirtualWallboxDataBlock(state, "holding", zero_mode=False)
    block.setValues(5005, [SESSION_COMMAND_START_VALUE])

    charging_state = state.read_block("input", 1001, 1)[0]
    assert charging_state == 1


def test_device_context_uses_single_offset() -> None:
    """Device context should not offset Modbus addresses twice."""

    scenario = build_default_scenario()
    state = scenario.create_state()
    state.apply_values({"charging_state": 1})
    input_block = VirtualWallboxDataBlock(state, "input", zero_mode=False)
    holding_block = VirtualWallboxDataBlock(state, "holding", zero_mode=False)
    context = VirtualWallboxDeviceContext(
        zero_mode=False,
        input_block=input_block,
        holding_block=holding_block,
    )

    assert context.getValues(4, 1000, 1) == [1]

    context.setValues(6, 5005, [SESSION_COMMAND_START_VALUE])
    assert state.read_block("input", 1001, 1)[0] == 1
