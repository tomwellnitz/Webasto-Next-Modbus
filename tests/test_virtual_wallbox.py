"""Integration style tests using the virtual wallbox simulator."""

from __future__ import annotations

import pytest

from custom_components.webasto_next_modbus.const import SESSION_COMMAND_START_VALUE, get_register
from custom_components.webasto_next_modbus.hub import ModbusBridge
from virtual_wallbox.server import VirtualWallboxDataBlock
from virtual_wallbox.simulator import (
	FakeAsyncModbusTcpClient,
	FakeModbusException,
	Scenario,
	build_default_scenario,
	register_virtual_wallbox,
)


async def _make_bridge(
	monkeypatch: pytest.MonkeyPatch,
	host: str,
	port: int,
	unit_id: int,
) -> ModbusBridge:
	"""Create a Modbus bridge with the fake pymodbus client injected."""

	# Reset cached client classes inside the hub module.
	from custom_components.webasto_next_modbus import hub as hub_module

	monkeypatch.setattr(hub_module, "_ASYNC_CLIENT_CLASS", None)
	monkeypatch.setattr(hub_module, "_MODBUS_EXCEPTION_CLASS", None)

	def _ensure_fake():
		return FakeAsyncModbusTcpClient, FakeModbusException

	monkeypatch.setattr(hub_module, "_ensure_pymodbus", _ensure_fake)
	return ModbusBridge(host, port, unit_id)


@pytest.mark.asyncio
async def test_bridge_reads_data_from_virtual_wallbox(
	default_virtual_wallbox,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""The Modbus bridge should decode values provided by the simulator."""

	host = "127.0.0.1"
	port = 15020
	unit = default_virtual_wallbox.unit_id

	bridge = await _make_bridge(monkeypatch, host, port, unit)
	data = await bridge.async_read_data()

	assert data["serial_number"] == "SIM-WB-0001"
	assert data["charging_state"] == 0
	assert data["active_power_total_w"] == 0


@pytest.mark.asyncio
async def test_bridge_write_actions_update_simulated_state(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Writing the session command should flip charging related registers."""

	scenario = build_default_scenario()
	host = "192.0.2.1"
	port = 5020

	with register_virtual_wallbox(host=host, port=port, scenario=scenario) as state:
		bridge = await _make_bridge(monkeypatch, host, port, state.unit_id)
		await bridge.async_write_register(get_register("session_command"), 1)
		data = await bridge.async_read_data()
		assert data["charging_state"] == 1
		assert data["charge_point_state"] == 2

		await bridge.async_write_register(get_register("session_command"), 2)
		data_after_stop = await bridge.async_read_data()
		assert data_after_stop["charging_state"] == 0
		assert data_after_stop["charge_point_state"] == 0


@pytest.mark.asyncio
async def test_custom_scenario_values_are_exposed(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Scenarios may override any register exposed through the bridge."""

	sim = Scenario(
		values={
			"serial_number": "WB-TEST-999",
			"charging_state": 1,
			"active_power_total_w": 11800,
		},
	)
	host = "198.51.100.44"
	port = 18000

	with register_virtual_wallbox(host=host, port=port, scenario=sim) as state:
		bridge = await _make_bridge(monkeypatch, host, port, state.unit_id)
		payload = await bridge.async_read_data()

	assert payload["serial_number"] == "WB-TEST-999"
	assert payload["active_power_total_w"] == 11800
	assert payload["charging_state"] == 1

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
