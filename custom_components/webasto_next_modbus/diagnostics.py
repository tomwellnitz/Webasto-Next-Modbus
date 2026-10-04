"""Diagnostics support for the Webasto Next Modbus integration."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from . import WebastoConfigEntry
from .const import CONF_REST_PASSWORD, CONF_REST_USERNAME

TO_REDACT = {
    CONF_HOST,
    CONF_REST_PASSWORD,
    CONF_REST_USERNAME,
    # RFID tag of the last user (Modbus) and the free-charging tag (REST).
    "session_user_id",
    "free_charging_tag_id",
    # Network identifiers reported by the REST API.
    "ip_address",
    "mac_address_ethernet",
    "mac_address_wifi",
}


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _redact_host(text: str | None, host: str) -> str | None:
    """Remove the wallbox address from free-form error messages."""

    if not text or not host:
        return text
    return text.replace(host, REDACTED)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: WebastoConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""

    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    host = str(entry.data.get(CONF_HOST, ""))

    rest = runtime.rest_coordinator
    rest_data = rest.data if rest is not None else None

    return {
        "config_entry": {
            "version": f"{entry.version}.{entry.minor_version}",
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "runtime": {
            "model": runtime.model,
            "variant": runtime.variant,
            "max_current": runtime.max_current,
            "last_success": _iso_or_none(coordinator.last_success),
            "last_failure": _iso_or_none(coordinator.last_failure),
            "consecutive_failures": coordinator.consecutive_failures,
            "last_error": _redact_host(coordinator.last_error, host),
        },
        "registers": async_redact_data(dict(coordinator.data or {}), TO_REDACT),
        "rest": {
            "enabled": rest is not None,
            "last_update_success": rest.last_update_success if rest is not None else None,
            "data": (
                async_redact_data(asdict(rest_data), TO_REDACT) if rest_data is not None else None
            ),
        },
    }
