"""Integration tests that run the config entry inside a real Home Assistant."""

from __future__ import annotations

from collections.abc import AsyncGenerator
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
from tests.conftest import HA_HOST, HA_PORT, HA_UNIT_ID
from virtual_wallbox.simulator import VirtualWallboxState

HOST = HA_HOST
PORT = HA_PORT
UNIT_ID = HA_UNIT_ID

pytestmark = pytest.mark.usefixtures("enable_custom_integrations", "fake_pymodbus")


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
    assert diagnostics["rest"] == {"enabled": False, "last_update_success": None, "data": None}


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


async def test_migration_keeps_entities_and_device_but_drops_host_from_ids(
    hass: HomeAssistant, wallbox: VirtualWallboxState
) -> None:
    """1.2 entries move to entry-ID based identities without new entities or devices."""

    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Wallbox",
        unique_id=f"{HOST}-{UNIT_ID}",
        version=1,
        minor_version=2,
        data={
            CONF_HOST: HOST,
            CONF_PORT: PORT,
            CONF_UNIT_ID: UNIT_ID,
            CONF_SCAN_INTERVAL: 10,
            CONF_VARIANT: VARIANT_22_KW,
            CONF_MODEL: MODEL_NEXT,
        },
    )
    entry.add_to_hass(hass)
    old_slug = f"{HOST}-{UNIT_ID}"
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, old_slug)}, name="Wallbox"
    )
    sensor = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{old_slug}-charge_point_state",
        config_entry=entry,
        device_id=device.id,
        suggested_object_id="wallbox_charge_point_state",
    )
    legacy_tag = entity_registry.async_get_or_create(
        "text",
        DOMAIN,
        f"{HOST}_{UNIT_ID}_free_charging_tag_id",
        config_entry=entry,
        device_id=device.id,
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.minor_version == CONFIG_ENTRY_MINOR_VERSION
    migrated = entity_registry.async_get(sensor.entity_id)
    assert migrated is not None
    assert migrated.unique_id == f"{entry.entry_id}-charge_point_state"
    assert entity_registry.async_get(legacy_tag.entity_id).unique_id == (
        f"{entry.entry_id}-rest-free_charging_tag_id"
    )
    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    assert [d.id for d in devices] == [device.id]
    assert devices[0].identifiers == {(DOMAIN, entry.entry_id)}
    # The entity keeps its entity_id and is backed by live data again.
    assert hass.states.get(sensor.entity_id).state == "available"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_reconfigure_to_new_host_keeps_entities(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """Changing the IP keeps the same device, entity IDs and history."""

    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    from virtual_wallbox.simulator import register_virtual_wallbox

    entity_registry = er.async_get(hass)
    before = {
        e.entity_id: e.unique_id
        for e in er.async_entries_for_config_entry(entity_registry, loaded_entry.entry_id)
    }

    with register_virtual_wallbox(host="192.0.2.99", port=PORT):
        result = await loaded_entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.0.2.99", CONF_PORT: PORT, CONF_UNIT_ID: UNIT_ID, CONF_NAME: ""},
        )
        await hass.async_block_till_done()
        assert result["reason"] == "reconfigure_successful"
        assert loaded_entry.data[CONF_HOST] == "192.0.2.99"

        after = {
            e.entity_id: e.unique_id
            for e in er.async_entries_for_config_entry(entity_registry, loaded_entry.entry_id)
        }
        assert after == before
        devices = dr.async_entries_for_config_entry(dr.async_get(hass), loaded_entry.entry_id)
        assert len(devices) == 1
        assert hass.states.get("sensor.wallbox_charge_point_state").state == "available"

        assert await hass.config_entries.async_unload(loaded_entry.entry_id)
        await hass.async_block_till_done()


async def test_only_stale_devices_can_be_removed(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    from homeassistant.helpers import device_registry as dr

    from custom_components.webasto_next_modbus import async_remove_config_entry_device

    device_registry = dr.async_get(hass)
    current = dr.async_entries_for_config_entry(device_registry, loaded_entry.entry_id)[0]
    stale = device_registry.async_get_or_create(
        config_entry_id=loaded_entry.entry_id, identifiers={(DOMAIN, "198.51.100.1-255")}
    )

    assert not await async_remove_config_entry_device(hass, loaded_entry, current)
    assert await async_remove_config_entry_device(hass, loaded_entry, stale)
