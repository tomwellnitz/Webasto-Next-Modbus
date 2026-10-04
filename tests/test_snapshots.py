"""Snapshot tests for entities, the device and diagnostics.

Any change to an entity's unique ID, name, category, unit, device class or
state shows up as a snapshot diff. Regenerate after an intended change with
``pytest tests/test_snapshots.py --snapshot-update`` and review the diff.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import PropertyMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
from syrupy.assertion import SnapshotAssertion

from custom_components.webasto_next_modbus.const import (
    CONF_MODEL,
    CONF_REST_ENABLED,
    CONF_REST_PASSWORD,
    CONF_REST_USERNAME,
    CONF_SCAN_INTERVAL,
    CONF_VARIANT,
    MODEL_NEXT,
    MODEL_UNITE,
    VARIANT_22_KW,
)
from tests.conftest import HA_HOST, make_config_entry

pytestmark = pytest.mark.usefixtures("enable_custom_integrations", "fake_pymodbus", "wallbox")

ENTRY_ID = "01JWEBASTOSNAPSHOTENTRY000"
BASE = f"https://{HA_HOST}/api"
JSON = {"Content-Type": "application/json"}


def _options(model: str) -> dict[str, Any]:
    return {
        CONF_SCAN_INTERVAL: 10,
        CONF_VARIANT: VARIANT_22_KW,
        CONF_MODEL: model,
        CONF_REST_ENABLED: True,
        CONF_REST_USERNAME: "admin",
        CONF_REST_PASSWORD: "secret",
    }


def _mock_next_api(aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(f"{BASE}/login", json={"access_token": "token"}, headers=JSON)
    aioclient_mock.get(
        f"{BASE}/sections/system",
        json=[
            {"fieldKey": "comboard-sw-version", "value": "3.1.27"},
            {"fieldKey": "comboard-hw-version", "value": "2"},
            {"fieldKey": "powerboard-sw-version", "value": "1.2.3"},
            {"fieldKey": "powerboard-hw-version", "value": "4"},
            {"fieldKey": "MAC-Address Eth0", "value": "AA:BB:CC:DD:EE:FF"},
            {"fieldKey": "led-brightness", "value": 40},
        ],
        headers=JSON,
    )
    aioclient_mock.get(
        f"{BASE}/sections/auth",
        json=[
            {"fieldKey": "free-charging", "value": "true"},
            {"fieldKey": "free-charging-alais", "value": "TAG-0001"},
        ],
        headers=JSON,
    )
    aioclient_mock.get(f"{BASE}/current-errors", json=[], headers=JSON)


def _mock_unite_api(aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(f"{BASE}/login", json={"access_token": "token"}, headers=JSON)
    aioclient_mock.get(
        f"{BASE}/configuration-fields/",
        json=[
            {"fieldKey": "ocppConfigurations.freeModeActive", "value": "TRUE"},
            {"fieldKey": "ocppConfigurations.freeModeRfid", "value": "TAG-0001"},
            {"fieldKey": "generalSettings.ledDimmingLevel", "value": "mid"},
            {"fieldKey": "generalSettings.randomisedDelayMaximumDuration", "value": "600"},
        ],
        headers=JSON,
    )


@pytest.fixture(autouse=True)
def _enable_all_entities() -> Generator[None]:
    """Create disabled-by-default entities too, so they are covered as well."""

    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        new_callable=PropertyMock,
        return_value=True,
    ):
        yield


async def _setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, model: str
) -> MockConfigEntry:
    if model == MODEL_UNITE:
        _mock_unite_api(aioclient_mock)
    else:
        _mock_next_api(aioclient_mock)
    entry: MockConfigEntry = make_config_entry(
        options=_options(model), model=model, entry_id=ENTRY_ID
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    rest = entry.runtime_data.rest_coordinator
    assert rest is not None
    assert rest.initial_refresh is not None
    await rest.initial_refresh
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


async def _unload(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize("model", [MODEL_NEXT, MODEL_UNITE])
async def test_entities(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    snapshot: SnapshotAssertion,
    model: str,
) -> None:
    """Every entity's registry entry and state matches the snapshot."""

    entry = await _setup(hass, aioclient_mock, model)

    entity_entries = sorted(
        er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id),
        key=lambda item: item.entity_id,
    )
    assert entity_entries
    for entity_entry in entity_entries:
        assert entity_entry == snapshot(name=f"{entity_entry.entity_id}-entry")
        state = hass.states.get(entity_entry.entity_id)
        assert state is not None, entity_entry.entity_id
        assert state == snapshot(name=f"{entity_entry.entity_id}-state")

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert devices == snapshot(name="devices")

    await _unload(hass, entry)


async def test_diagnostics(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    hass_client: ClientSessionGenerator,
    snapshot: SnapshotAssertion,
) -> None:
    """The diagnostics download matches the snapshot (and stays redacted)."""

    entry = await _setup(hass, aioclient_mock, MODEL_NEXT)
    assert await async_setup_component(hass, "diagnostics", {})

    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    runtime = diagnostics["runtime"]
    # Timestamps of the last poll differ on every run.
    runtime["last_success"] = "<timestamp>" if runtime["last_success"] else None
    assert diagnostics == snapshot

    await _unload(hass, entry)
