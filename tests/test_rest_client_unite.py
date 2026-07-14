"""Tests for the model-aware REST client (Next vs Unite)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.webasto_next_modbus.const import MODEL_NEXT, MODEL_UNITE
from custom_components.webasto_next_modbus.rest_client import RestClient, RestClientError

pytestmark = pytest.mark.asyncio

# A trimmed sample of the Unite's GET /api/configuration-fields/ response
# (scrubbed dump from issue #97).
UNITE_FIELDS = [
    {"fieldKey": "wifiSettings.ssid", "value": "irrelevant"},
    {"fieldKey": "ocppConfigurations.freeModeActive", "value": "FALSE"},
    {"fieldKey": "ocppConfigurations.freeModeRfid", "value": "TAG-123"},
    {"fieldKey": "generalSettings.ledDimmingLevel", "value": "mid"},
    {"fieldKey": "generalSettings.randomisedDelayMaximumDuration", "value": 0},
]


def _unite_client() -> RestClient:
    client = RestClient("host", "admin", "pw", MagicMock(), model=MODEL_UNITE)
    client._ensure_token = AsyncMock()  # type: ignore[method-assign]
    return client


def _next_client() -> RestClient:
    client = RestClient("host", "admin", "pw", MagicMock(), model=MODEL_NEXT)
    client._ensure_token = AsyncMock()  # type: ignore[method-assign]
    return client


async def test_unite_get_data_parses_configuration_fields() -> None:
    client = _unite_client()
    client._get = AsyncMock(return_value=UNITE_FIELDS)  # type: ignore[method-assign]

    data = await client.get_data()

    client._get.assert_awaited_once_with("/configuration-fields/")
    assert data.free_charging_enabled is False
    assert data.free_charging_tag_id == "TAG-123"
    assert data.led_dimming_level == "mid"
    assert data.randomised_delay == 0
    # Diagnostic sensors are not available on the Unite.
    assert data.comboard_sw_version is None


async def test_unite_free_charging_true_parses() -> None:
    client = _unite_client()
    client._get = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"fieldKey": "ocppConfigurations.freeModeActive", "value": "TRUE"}]
    )

    data = await client.get_data()

    assert data.free_charging_enabled is True


async def test_unite_unknown_led_level_is_dropped() -> None:
    client = _unite_client()
    client._get = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"fieldKey": "generalSettings.ledDimmingLevel", "value": "bogus"}]
    )

    data = await client.get_data()

    assert data.led_dimming_level is None


async def test_unite_set_free_charging_payload() -> None:
    client = _unite_client()
    client._update_config = AsyncMock()  # type: ignore[method-assign]

    await client.set_free_charging(enabled=False)

    client._update_config.assert_awaited_once_with(
        [
            {
                "fieldKey": "ocppConfigurations.freeModeActive",
                "value": "FALSE",
                "configurationFieldUpdateType": "simple-configuration-field-update",
            }
        ]
    )


async def test_unite_set_free_charging_tag_payload() -> None:
    client = _unite_client()
    client._update_config = AsyncMock()  # type: ignore[method-assign]

    await client.set_free_charging_tag_id("NEW-TAG")

    client._update_config.assert_awaited_once_with(
        [
            {
                "fieldKey": "ocppConfigurations.freeModeRfid",
                "value": "NEW-TAG",
                "configurationFieldUpdateType": "simple-configuration-field-update",
            }
        ]
    )


async def test_unite_set_led_dimming_payload() -> None:
    client = _unite_client()
    client._update_config = AsyncMock()  # type: ignore[method-assign]

    await client.set_led_dimming_level("veryLow")

    client._update_config.assert_awaited_once_with(
        [
            {
                "fieldKey": "generalSettings.ledDimmingLevel",
                "value": "veryLow",
                "configurationFieldUpdateType": "simple-configuration-field-update",
            }
        ]
    )


async def test_unite_set_led_dimming_rejects_unknown_level() -> None:
    client = _unite_client()
    client._update_config = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(ValueError):
        await client.set_led_dimming_level("bogus")
    client._update_config.assert_not_awaited()


async def test_unite_set_randomised_delay_payload() -> None:
    client = _unite_client()
    client._update_config = AsyncMock()  # type: ignore[method-assign]

    await client.set_randomised_delay(600)

    client._update_config.assert_awaited_once_with(
        [
            {
                "fieldKey": "generalSettings.randomisedDelayMaximumDuration",
                "value": "600",
                "configurationFieldUpdateType": "simple-configuration-field-update",
            }
        ]
    )


async def test_unite_set_randomised_delay_out_of_range() -> None:
    client = _unite_client()
    client._update_config = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(ValueError):
        await client.set_randomised_delay(3600)
    client._update_config.assert_not_awaited()


async def test_unite_led_brightness_not_supported() -> None:
    client = _unite_client()
    client._update_config = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(RestClientError):
        await client.set_led_brightness(50)
    client._update_config.assert_not_awaited()


async def test_unite_unknown_bool_is_none() -> None:
    client = _unite_client()
    client._get = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"fieldKey": "ocppConfigurations.freeModeActive", "value": "maybe"}]
    )

    data = await client.get_data()

    assert data.free_charging_enabled is None


async def test_next_led_dimming_not_supported() -> None:
    client = _next_client()
    client._update_config = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(RestClientError):
        await client.set_led_dimming_level("mid")
    client._update_config.assert_not_awaited()


async def test_next_randomised_delay_not_supported() -> None:
    client = _next_client()
    client._update_config = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(RestClientError):
        await client.set_randomised_delay(60)
    client._update_config.assert_not_awaited()


async def test_next_set_free_charging_uses_boolean_update_type() -> None:
    client = _next_client()
    client._update_config = AsyncMock()  # type: ignore[method-assign]

    await client.set_free_charging(enabled=True)

    client._update_config.assert_awaited_once_with(
        [
            {
                "fieldKey": "free-charging",
                "value": True,
                "configurationFieldUpdateType": "boolean-configuration-field-update",
            }
        ]
    )


async def test_next_get_data_uses_sections() -> None:
    client = _next_client()
    client._get_section = AsyncMock(return_value=[])  # type: ignore[method-assign]
    client._get_current_errors = AsyncMock(return_value=[])  # type: ignore[method-assign]

    await client.get_data()

    # Next reads the per-section endpoints, not the Unite's flat one.
    assert client._get_section.await_count == 2
