"""Integration tests that run the config entry inside a real Home Assistant."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.webasto_next_modbus import CONFIG_ENTRY_MINOR_VERSION
from custom_components.webasto_next_modbus import hub as hub_module
from custom_components.webasto_next_modbus.const import (
    CONF_MODEL,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_UNIT_ID,
    CONF_VARIANT,
    DOMAIN,
    FAILURE_ISSUE_THRESHOLD,
    MODEL_NEXT,
    SESSION_COMMAND_START_VALUE,
    VARIANT_22_KW,
)
from virtual_wallbox.simulator import (
    FakeAsyncModbusTcpClient,
    FakeModbusException,
    VirtualWallboxState,
    build_default_scenario,
    register_virtual_wallbox,
)

HOST = "192.0.2.10"
PORT = 502
UNIT_ID = 255


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the integration from custom_components."""


@pytest.fixture(autouse=True)
def fake_pymodbus() -> Generator[None]:
    """Route the bridge's Modbus client to the virtual wallbox."""

    with patch.object(
        hub_module,
        "_ensure_pymodbus",
        return_value=(FakeAsyncModbusTcpClient, FakeModbusException),
    ):
        yield


@pytest.fixture
def wallbox() -> Generator[VirtualWallboxState]:
    """Provide a virtual Webasto Next at HOST:PORT."""

    with register_virtual_wallbox(
        host=HOST, port=PORT, scenario=build_default_scenario(unit_id=UNIT_ID)
    ) as state:
        yield state


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Wallbox",
        unique_id=f"{HOST}-{UNIT_ID}",
        version=1,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
        data={
            CONF_HOST: HOST,
            CONF_PORT: PORT,
            CONF_UNIT_ID: UNIT_ID,
            CONF_SCAN_INTERVAL: 10,
            CONF_VARIANT: VARIANT_22_KW,
            CONF_MODEL: MODEL_NEXT,
        },
    )


@pytest.fixture
async def loaded_entry(
    hass: HomeAssistant, wallbox: VirtualWallboxState, config_entry: MockConfigEntry
) -> AsyncGenerator[MockConfigEntry]:
    """Set the entry up against the virtual wallbox and unload it afterwards."""

    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED
    yield config_entry
    if config_entry.state is ConfigEntryState.LOADED:
        assert await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()


async def test_setup_and_unload(hass: HomeAssistant, loaded_entry: MockConfigEntry) -> None:
    """The entry loads, creates entities and unloads cleanly."""

    state = hass.states.get("sensor.wallbox_charge_point_state")
    assert state is not None
    assert state.state == "available"

    assert await hass.config_entries.async_unload(loaded_entry.entry_id)
    await hass.async_block_till_done()
    assert loaded_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retries_when_wallbox_unreachable(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """An unreachable wallbox leaves the entry in setup retry, without notifications."""

    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert config_entry.reason is not None
    assert "Could not connect to the wallbox" in config_entry.reason
    assert not hass.states.async_all("persistent_notification")


async def test_migrate_minor_version_1(hass: HomeAssistant, wallbox: VirtualWallboxState) -> None:
    """Entries from before 1.2 get model/variant stored and an empty name dropped."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Wallbox",
        version=1,
        minor_version=1,
        data={
            CONF_HOST: HOST,
            CONF_PORT: PORT,
            CONF_UNIT_ID: UNIT_ID,
            CONF_SCAN_INTERVAL: 10,
            CONF_NAME: "",
        },
        options={CONF_VARIANT: VARIANT_22_KW},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.minor_version == CONFIG_ENTRY_MINOR_VERSION
    assert entry.data[CONF_VARIANT] == VARIANT_22_KW
    assert entry.data[CONF_MODEL] == MODEL_NEXT
    assert CONF_NAME not in entry.data

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_set_current_accepts_rendered_template_value(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, wallbox: VirtualWallboxState
) -> None:
    """A float such as a rendered ``{{ states('input_number.x') }}`` is accepted."""

    await hass.services.async_call(DOMAIN, "set_current", {"amps": 16.0}, blocking=True)

    assert wallbox.read_block("holding", 5004, 1) == [16]


@pytest.mark.parametrize("amps", [1, 5])
async def test_set_current_rejects_values_below_minimum(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, amps: int
) -> None:
    """1-5 A is below the IEC 61851 minimum and is rejected, 0 still pauses."""

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(DOMAIN, "set_current", {"amps": amps}, blocking=True)
    assert exc_info.value.translation_key == "current_below_minimum"

    await hass.services.async_call(DOMAIN, "set_current", {"amps": 0}, blocking=True)


async def test_unknown_config_entry_id_is_rejected(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """An explicit config_entry_id must match a loaded wallbox."""

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            "set_current",
            {"amps": 10, "config_entry_id": "does-not-exist"},
            blocking=True,
        )
    assert exc_info.value.translation_key == "entry_not_found"


async def test_start_session_produces_change_on_register(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, wallbox: VirtualWallboxState
) -> None:
    """Start writes 0 then 1, so it also works when 5006 already holds 1."""

    wallbox.write_register(5006, SESSION_COMMAND_START_VALUE)
    writes: list[tuple[int, int]] = []
    original = wallbox.write_register

    def _record(address: int, value: int) -> None:
        writes.append((address, value))
        original(address, value)

    with (
        patch.object(wallbox, "write_register", side_effect=_record),
        patch.object(hub_module.asyncio, "sleep", AsyncMock()),
    ):
        await hass.services.async_call(DOMAIN, "start_session", {}, blocking=True)

    assert [w for w in writes if w[0] == 5006] == [(5006, 0), (5006, SESSION_COMMAND_START_VALUE)]


async def test_repair_issue_lifecycle(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, wallbox: VirtualWallboxState
) -> None:
    """Repeated poll failures raise a repair issue that clears on recovery."""

    coordinator = loaded_entry.runtime_data.coordinator
    issue_id = f"connection_failed_{loaded_entry.entry_id}"
    issue_registry = ir.async_get(hass)

    with patch.object(
        loaded_entry.runtime_data.bridge,
        "async_read_data",
        AsyncMock(side_effect=hub_module.WebastoModbusError("offline")),
    ):
        for _ in range(FAILURE_ISSUE_THRESHOLD):
            await coordinator.async_refresh()

    issue = issue_registry.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_key == "connection_failed"

    await coordinator.async_refresh()
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None


async def test_diagnostics_are_redacted(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    loaded_entry: MockConfigEntry,
    wallbox: VirtualWallboxState,
) -> None:
    """Diagnostics never contain the host, credentials or the RFID tag."""

    wallbox.apply_values({"session_user_id": "TAG-1234"})
    coordinator = loaded_entry.runtime_data.coordinator
    await coordinator.async_refresh()
    coordinator.last_error = f"Failed to connect to {HOST}:{PORT}: refused"

    assert await async_setup_component(hass, "diagnostics", {})
    diagnostics: dict[str, Any] = await get_diagnostics_for_config_entry(
        hass, hass_client, loaded_entry
    )

    assert diagnostics["config_entry"]["data"][CONF_HOST] == "**REDACTED**"
    assert diagnostics["registers"]["session_user_id"] == "**REDACTED**"
    assert HOST not in str(diagnostics)
    assert "TAG-1234" not in str(diagnostics)
    assert diagnostics["rest"] == {"enabled": False, "data": None}


async def test_options_change_reloads_once(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """Renaming via the options flow updates data and options in a single reload."""

    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload_mock:
        result = await hass.config_entries.options.async_init(loaded_entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_SCAN_INTERVAL: 15,
                CONF_MODEL: MODEL_NEXT,
                CONF_VARIANT: VARIANT_22_KW,
                CONF_NAME: "Garage",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    assert loaded_entry.title == "Garage"
    assert loaded_entry.options[CONF_SCAN_INTERVAL] == 15
    reload_mock.assert_awaited_once_with(loaded_entry.entry_id)


async def test_repair_issue_removed_when_entry_unloaded_or_deleted(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """An issue raised while offline doesn't outlive the entry."""

    coordinator = loaded_entry.runtime_data.coordinator
    issue_id = f"connection_failed_{loaded_entry.entry_id}"
    issue_registry = ir.async_get(hass)

    with patch.object(
        loaded_entry.runtime_data.bridge,
        "async_read_data",
        AsyncMock(side_effect=hub_module.WebastoModbusError("offline")),
    ):
        for _ in range(FAILURE_ISSUE_THRESHOLD):
            await coordinator.async_refresh()
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is not None

    assert await hass.config_entries.async_remove(loaded_entry.entry_id)
    await hass.async_block_till_done()

    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None
