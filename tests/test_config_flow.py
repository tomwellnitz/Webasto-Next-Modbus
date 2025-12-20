"""Config flow tests for the Webasto Next Modbus integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)

from custom_components.webasto_next_modbus.config_flow import (
    CannotConnect,
    WebastoConfigFlow,
    WebastoOptionsFlow,
)
from custom_components.webasto_next_modbus.const import (
    CONF_REST_ENABLED,
    CONF_SCAN_INTERVAL,
    CONF_UNIT_ID,
    CONF_VARIANT,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DEFAULT_VARIANT,
    VARIANT_22_KW,
)

pytestmark = pytest.mark.asyncio


async def test_user_step_success() -> None:
    """Verify the config flow creates an entry on successful validation."""

    flow = WebastoConfigFlow()
    flow.hass = MagicMock()

    user_input = {
        CONF_HOST: "192.0.2.1",
        CONF_PORT: 1502,
        CONF_UNIT_ID: 10,
        CONF_SCAN_INTERVAL: 5,
        CONF_VARIANT: VARIANT_22_KW,
    }

    with (
        patch.object(WebastoConfigFlow, "_async_validate_and_connect", AsyncMock()) as validate,
        patch.object(WebastoConfigFlow, "async_set_unique_id", AsyncMock()) as set_unique,
        patch.object(WebastoConfigFlow, "_abort_if_unique_id_configured") as abort,
    ):
        result = await flow.async_step_user(user_input)

    validate.assert_awaited_once()
    set_unique.assert_awaited_once_with("192.0.2.1-10")
    abort.assert_called_once()

    assert result.get("type") == FlowResultType.CREATE_ENTRY
    assert result.get("title") == "192.0.2.1 (unit 10)"
    assert result.get("data") == user_input
    assert result.get("options") == {CONF_SCAN_INTERVAL: 5, CONF_VARIANT: VARIANT_22_KW}


async def test_user_step_cannot_connect() -> None:
    """Return form with error when validation fails."""

    flow = WebastoConfigFlow()
    flow.hass = MagicMock()

    with patch.object(
        WebastoConfigFlow,
        "_async_validate_and_connect",
        AsyncMock(side_effect=CannotConnect),
    ):
        result = await flow.async_step_user(
            {
                CONF_HOST: "192.0.2.2",
                CONF_PORT: DEFAULT_PORT,
                CONF_UNIT_ID: DEFAULT_UNIT_ID,
                CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            }
        )

    assert result.get("type") == FlowResultType.FORM
    assert result.get("errors") == {"base": "cannot_connect"}


async def test_options_flow_updates_interval() -> None:
    """Ensure options flow stores the chosen scan interval."""

    entry = MockConfigEntry(
        domain="webasto_next_modbus",
        data={
            CONF_HOST: "192.0.2.3",
            CONF_PORT: DEFAULT_PORT,
            CONF_UNIT_ID: DEFAULT_UNIT_ID,
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            CONF_VARIANT: DEFAULT_VARIANT,
        },
        options={
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            CONF_VARIANT: DEFAULT_VARIANT,
        },
        unique_id="192.0.2.3-255",
    )

    options_flow = WebastoOptionsFlow(entry)
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    options_flow.hass = hass

    initial = await options_flow.async_step_init()
    assert initial.get("type") == FlowResultType.FORM

    updated = await options_flow.async_step_init(
        {CONF_SCAN_INTERVAL: 10, CONF_VARIANT: VARIANT_22_KW}
    )
    assert updated.get("type") == FlowResultType.CREATE_ENTRY
    assert updated.get("data") == {
        CONF_SCAN_INTERVAL: 10,
        CONF_VARIANT: VARIANT_22_KW,
        CONF_REST_ENABLED: False,
    }
    hass.config_entries.async_update_entry.assert_called_once()
