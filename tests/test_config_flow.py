"""Config flow tests for the Webasto Next Modbus integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
import voluptuous as vol
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
    CONF_MODEL,
    CONF_REST_ENABLED,
    CONF_REST_PASSWORD,
    CONF_REST_USERNAME,
    CONF_SCAN_INTERVAL,
    CONF_UNIT_ID,
    CONF_VARIANT,
    DEFAULT_MODEL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DEFAULT_VARIANT,
    VARIANT_22_KW,
)
from custom_components.webasto_next_modbus.rest_client import AuthenticationError

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
        CONF_MODEL: DEFAULT_MODEL,
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
    assert result.get("options") == {
        CONF_SCAN_INTERVAL: 5,
        CONF_VARIANT: VARIANT_22_KW,
        CONF_MODEL: DEFAULT_MODEL,
    }


async def test_user_step_unite_model() -> None:
    """The model selector is stored and exposed on the created entry."""

    flow = WebastoConfigFlow()
    flow.hass = MagicMock()

    user_input = {
        CONF_HOST: "192.0.2.4",
        CONF_PORT: DEFAULT_PORT,
        CONF_UNIT_ID: DEFAULT_UNIT_ID,
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
        CONF_MODEL: "unite",
        CONF_VARIANT: VARIANT_22_KW,
    }

    with (
        patch.object(WebastoConfigFlow, "_async_validate_and_connect", AsyncMock()),
        patch.object(WebastoConfigFlow, "async_set_unique_id", AsyncMock()),
        patch.object(WebastoConfigFlow, "_abort_if_unique_id_configured"),
    ):
        result = await flow.async_step_user(user_input)

    assert result.get("type") == FlowResultType.CREATE_ENTRY
    assert result.get("data", {}).get(CONF_MODEL) == "unite"
    assert result.get("options", {}).get(CONF_MODEL) == "unite"


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


async def test_reconfigure_shows_form() -> None:
    """The reconfigure step shows a pre-filled form when no input is given."""

    entry = MockConfigEntry(
        domain="webasto_next_modbus",
        data={
            CONF_HOST: "192.0.2.3",
            CONF_PORT: DEFAULT_PORT,
            CONF_UNIT_ID: DEFAULT_UNIT_ID,
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            CONF_VARIANT: DEFAULT_VARIANT,
            CONF_MODEL: DEFAULT_MODEL,
        },
        unique_id="192.0.2.3-255",
    )

    flow = WebastoConfigFlow()
    flow.hass = MagicMock()

    with patch.object(WebastoConfigFlow, "_get_reconfigure_entry", return_value=entry):
        result = await flow.async_step_reconfigure()

    assert result.get("type") == FlowResultType.FORM
    assert result.get("step_id") == "reconfigure"

    # The form is pre-filled with the entry's current connection settings.
    defaults = {
        marker.schema: marker.default()
        for marker in result["data_schema"].schema
        if getattr(marker, "default", vol.UNDEFINED) is not vol.UNDEFINED
    }
    assert defaults[CONF_HOST] == "192.0.2.3"
    assert defaults[CONF_PORT] == DEFAULT_PORT
    assert defaults[CONF_UNIT_ID] == DEFAULT_UNIT_ID


async def test_reconfigure_updates_connection() -> None:
    """Reconfigure updates host/port/unit_id; the update listener does the reload."""

    entry = MockConfigEntry(
        domain="webasto_next_modbus",
        data={
            CONF_HOST: "192.0.2.3",
            CONF_PORT: DEFAULT_PORT,
            CONF_UNIT_ID: DEFAULT_UNIT_ID,
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            CONF_VARIANT: DEFAULT_VARIANT,
            CONF_MODEL: DEFAULT_MODEL,
        },
        unique_id="192.0.2.3-255",
    )

    flow = WebastoConfigFlow()
    flow.hass = MagicMock()

    with (
        patch.object(WebastoConfigFlow, "_get_reconfigure_entry", return_value=entry),
        patch.object(WebastoConfigFlow, "_async_current_entries", return_value=[entry]),
    ):
        result = await flow.async_step_reconfigure(
            {
                CONF_HOST: "192.0.2.99",
                CONF_PORT: 1502,
                CONF_UNIT_ID: 10,
            }
        )

    update = flow.hass.config_entries.async_update_entry
    update.assert_called_once()
    _, kwargs = update.call_args
    assert kwargs["data"][CONF_HOST] == "192.0.2.99"
    assert kwargs["data"][CONF_PORT] == 1502
    assert kwargs["data"][CONF_UNIT_ID] == 10
    assert kwargs["unique_id"] == "192.0.2.99-10"
    assert kwargs["title"] == "192.0.2.99 (unit 10)"
    assert result.get("type") == FlowResultType.ABORT
    assert result.get("reason") == "reconfigure_successful"


async def test_reconfigure_aborts_on_identity_collision() -> None:
    """Reconfiguring onto another entry's host/unit is rejected."""

    entry = MockConfigEntry(
        domain="webasto_next_modbus",
        data={
            CONF_HOST: "192.0.2.3",
            CONF_PORT: DEFAULT_PORT,
            CONF_UNIT_ID: DEFAULT_UNIT_ID,
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            CONF_VARIANT: DEFAULT_VARIANT,
            CONF_MODEL: DEFAULT_MODEL,
        },
        unique_id="192.0.2.3-255",
    )
    other = MockConfigEntry(
        domain="webasto_next_modbus",
        data={CONF_HOST: "192.0.2.50", CONF_UNIT_ID: 10},
        unique_id="192.0.2.50-10",
    )

    flow = WebastoConfigFlow()
    flow.hass = MagicMock()

    with (
        patch.object(WebastoConfigFlow, "_get_reconfigure_entry", return_value=entry),
        patch.object(WebastoConfigFlow, "_async_current_entries", return_value=[entry, other]),
    ):
        result = await flow.async_step_reconfigure(
            {
                CONF_HOST: "192.0.2.50",
                CONF_PORT: DEFAULT_PORT,
                CONF_UNIT_ID: 10,
            }
        )

    assert result.get("type") == FlowResultType.ABORT
    assert result.get("reason") == "already_configured"


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

    options_flow = WebastoOptionsFlow()
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    options_flow.hass = hass

    # Home Assistant 2024.12+ exposes `OptionsFlow.config_entry` as a
    # read-only property whose backing fields (`_config_entry_id`, `handler`)
    # are also read-only. For a unit-style test we patch the property to
    # return the MockConfigEntry directly.
    with patch.object(
        WebastoOptionsFlow,
        "config_entry",
        new_callable=PropertyMock,
        return_value=entry,
    ):
        initial = await options_flow.async_step_init()
        assert initial.get("type") == FlowResultType.FORM

        updated = await options_flow.async_step_init(
            {CONF_SCAN_INTERVAL: 10, CONF_VARIANT: VARIANT_22_KW}
        )

    assert updated.get("type") == FlowResultType.CREATE_ENTRY
    assert updated.get("data") == {
        CONF_SCAN_INTERVAL: 10,
        CONF_VARIANT: VARIANT_22_KW,
        CONF_MODEL: DEFAULT_MODEL,
        CONF_REST_ENABLED: False,
    }
    hass.config_entries.async_update_entry.assert_called_once()


async def test_reauth_shows_form() -> None:
    """The reauth step shows the credential form."""

    entry = MockConfigEntry(
        domain="webasto_next_modbus",
        data={CONF_HOST: "192.0.2.3", CONF_PORT: DEFAULT_PORT, CONF_UNIT_ID: DEFAULT_UNIT_ID},
        options={CONF_REST_ENABLED: True, CONF_REST_USERNAME: "admin"},
        unique_id="192.0.2.3-255",
    )

    flow = WebastoConfigFlow()
    flow.hass = MagicMock()

    with patch.object(WebastoConfigFlow, "_get_reauth_entry", return_value=entry):
        result = await flow.async_step_reauth_confirm()

    assert result.get("type") == FlowResultType.FORM
    assert result.get("step_id") == "reauth_confirm"


async def test_reauth_updates_credentials() -> None:
    """Reauth validates the new credentials and updates the entry options."""

    entry = MockConfigEntry(
        domain="webasto_next_modbus",
        data={CONF_HOST: "192.0.2.3", CONF_PORT: DEFAULT_PORT, CONF_UNIT_ID: DEFAULT_UNIT_ID},
        options={CONF_REST_ENABLED: True, CONF_REST_USERNAME: "admin"},
        unique_id="192.0.2.3-255",
    )

    flow = WebastoConfigFlow()
    flow.hass = MagicMock()

    with (
        patch.object(WebastoConfigFlow, "_get_reauth_entry", return_value=entry),
        patch.object(WebastoConfigFlow, "_async_validate_rest", AsyncMock()) as validate,
    ):
        result = await flow.async_step_reauth_confirm(
            {CONF_REST_USERNAME: "admin", CONF_REST_PASSWORD: "newpass"}
        )

    validate.assert_awaited_once()
    update = flow.hass.config_entries.async_update_entry
    update.assert_called_once()
    _, kwargs = update.call_args
    assert kwargs["options"][CONF_REST_USERNAME] == "admin"
    assert kwargs["options"][CONF_REST_PASSWORD] == "newpass"
    assert kwargs["options"][CONF_REST_ENABLED] is True
    assert result.get("type") == FlowResultType.ABORT
    assert result.get("reason") == "reauth_successful"


async def test_reauth_invalid_auth() -> None:
    """Rejected credentials re-show the reauth form with invalid_auth."""

    entry = MockConfigEntry(
        domain="webasto_next_modbus",
        data={CONF_HOST: "192.0.2.3", CONF_PORT: DEFAULT_PORT, CONF_UNIT_ID: DEFAULT_UNIT_ID},
        options={CONF_REST_ENABLED: True, CONF_REST_USERNAME: "admin"},
        unique_id="192.0.2.3-255",
    )

    flow = WebastoConfigFlow()
    flow.hass = MagicMock()

    with (
        patch.object(WebastoConfigFlow, "_get_reauth_entry", return_value=entry),
        patch.object(
            WebastoConfigFlow,
            "_async_validate_rest",
            AsyncMock(side_effect=AuthenticationError("bad creds")),
        ),
    ):
        result = await flow.async_step_reauth_confirm(
            {CONF_REST_USERNAME: "admin", CONF_REST_PASSWORD: "wrong"}
        )

    assert result.get("type") == FlowResultType.FORM
    assert result.get("step_id") == "reauth_confirm"
    assert result.get("errors") == {"base": "invalid_auth"}
