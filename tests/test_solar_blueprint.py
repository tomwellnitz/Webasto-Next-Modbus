"""Run the solar surplus blueprint as a real automation and check what it does."""

from __future__ import annotations

import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_mock_service

BLUEPRINT = (
    Path(__file__).resolve().parents[1]
    / "blueprints"
    / "automation"
    / "webasto_next_modbus"
    / "solar_optimizer.yaml"
)

GRID = "sensor.grid_power"
CURRENT = "number.wallbox_charging_current_limit"
PHASES = "sensor.wallbox_number_of_phases"
SWITCH = "switch.wallbox_three_phase_charging"


class Wallbox:
    """Records the current and phase writes the automation makes."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.current_calls: list[ServiceCall] = async_mock_service(hass, "number", "set_value")
        self.switch_on: list[ServiceCall] = async_mock_service(hass, "switch", "turn_on")
        self.switch_off: list[ServiceCall] = async_mock_service(hass, "switch", "turn_off")

    @property
    def currents(self) -> list[float]:
        return [call.data["value"] for call in self.current_calls]

    async def grid(self, watts: float) -> None:
        self.hass.states.async_set(GRID, str(watts), {"unit_of_measurement": "W"})
        await self.hass.async_block_till_done()


async def _setup(hass: HomeAssistant, **inputs: Any) -> Wallbox:
    target = Path(hass.config.path("blueprints/automation/webasto_next_modbus"))

    def _install() -> None:
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy(BLUEPRINT, target / BLUEPRINT.name)

    await hass.async_add_executor_job(_install)

    hass.states.async_set(GRID, "0", {"unit_of_measurement": "W"})
    wallbox = Wallbox(hass)
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "use_blueprint": {
                    "path": f"webasto_next_modbus/{BLUEPRINT.name}",
                    "input": {"current_entity": CURRENT, "grid_sensor": GRID, **inputs},
                }
            }
        },
    )
    await hass.async_block_till_done()
    return wallbox


def _set_current(hass: HomeAssistant, amps: float) -> None:
    hass.states.async_set(CURRENT, str(amps), {"unit_of_measurement": "A"})


async def test_follows_the_surplus(hass: HomeAssistant) -> None:
    """Fixed 690 W/A (three-phase): 690 W more export means 1 A more."""

    _set_current(hass, 10)
    wallbox = await _setup(hass)

    await wallbox.grid(-690)

    assert wallbox.currents == [11]


async def test_large_surplus_charges_at_the_maximum(hass: HomeAssistant) -> None:
    _set_current(hass, 10)
    wallbox = await _setup(hass, max_current=16)

    await wallbox.grid(-10000)

    assert wallbox.currents == [16]


@pytest.mark.parametrize(("below_minimum", "expected"), [("keep", 6), ("pause", 0)])
async def test_below_the_minimum(hass: HomeAssistant, below_minimum: str, expected: int) -> None:
    """1-5 A is not a valid current: keep 6 A or pause, never write 1-5 A."""

    _set_current(hass, 8)
    wallbox = await _setup(hass, below_minimum=below_minimum)

    await wallbox.grid(3000)  # (8 A x 690 W - 3000 W) / 690 = 3.7 A

    assert wallbox.currents == [expected]


async def test_keep_does_not_restart_paused_charging(hass: HomeAssistant) -> None:
    _set_current(hass, 0)
    wallbox = await _setup(hass)

    await wallbox.grid(100)

    assert wallbox.currents == []


async def test_paused_charging_resumes_with_enough_surplus(hass: HomeAssistant) -> None:
    _set_current(hass, 0)
    wallbox = await _setup(hass, below_minimum="pause")

    await wallbox.grid(-4500)

    assert wallbox.currents == [6]


async def test_phase_sensor_sets_watts_per_amp(hass: HomeAssistant) -> None:
    """Single-phase: 230 W per ampere instead of the fixed 690."""

    _set_current(hass, 10)
    hass.states.async_set(PHASES, "single_phase")
    wallbox = await _setup(hass, phase_sensor=PHASES)

    await wallbox.grid(-230)

    assert wallbox.currents == [11]


async def _setup_phase_switching(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    *,
    three_phase: bool,
    amps: float,
) -> Wallbox:
    _set_current(hass, amps)
    hass.states.async_set(PHASES, "three_phase" if three_phase else "single_phase")
    hass.states.async_set(SWITCH, "on" if three_phase else "off")
    freezer.tick(timedelta(minutes=11))
    return await _setup(hass, phase_sensor=PHASES, phase_switch=SWITCH, below_minimum="pause")


async def test_switches_to_single_phase_on_low_surplus(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """3 x 6 A needs ~4.1 kW; with ~3.1 kW available, charge single-phase."""

    wallbox = await _setup_phase_switching(hass, freezer, three_phase=True, amps=6)

    await wallbox.grid(1000)  # 6 A x 690 W - 1000 W = 3140 W available

    assert len(wallbox.switch_off) == 1
    assert wallbox.switch_off[0].data["entity_id"] == [SWITCH]
    assert wallbox.currents == [13]  # 3140 W / 230 V


async def test_switches_to_three_phase_on_high_surplus(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    wallbox = await _setup_phase_switching(hass, freezer, three_phase=False, amps=16)

    await wallbox.grid(-1500)  # 16 A x 230 W + 1500 W = 5180 W available

    assert len(wallbox.switch_on) == 1
    assert wallbox.currents == [7]  # 5180 W / 690 W per A


async def test_no_three_phase_without_headroom(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Just enough for 3 x 6 A is not enough: switching back needs 10 % headroom."""

    wallbox = await _setup_phase_switching(hass, freezer, three_phase=False, amps=16)

    await wallbox.grid(-600)  # 4280 W available, below 4140 W x 1.1

    assert wallbox.switch_on == []
    # Single-phase stays at its 16 A maximum (4280 W / 230 V = 18 A).
    assert wallbox.currents == []


async def test_phase_changes_respect_the_interval(hass: HomeAssistant) -> None:
    """A phase change right after the last one is not allowed."""

    _set_current(hass, 6)
    hass.states.async_set(PHASES, "three_phase")
    hass.states.async_set(SWITCH, "on")  # changed just now
    wallbox = await _setup(hass, phase_sensor=PHASES, phase_switch=SWITCH, below_minimum="pause")

    await wallbox.grid(1000)

    assert wallbox.switch_off == []
    assert wallbox.currents == [0]  # three-phase can't carry 6 A: pause instead
