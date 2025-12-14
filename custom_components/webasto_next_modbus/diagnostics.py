"""Diagnostics support for the Webasto Next Modbus integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import RuntimeData
from .const import DOMAIN

TO_REDACT = {"host"}


def _iso_or_none(value):
    return value.isoformat() if value else None


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""

    runtime: RuntimeData = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime.coordinator

    # Include current register values for debugging
    register_data: dict[str, Any] = {}
    if coordinator.data:
        register_data = dict(coordinator.data)

    return {
        "config_entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "runtime": {
            "variant": runtime.variant,
            "max_current": runtime.max_current,
            "last_success": _iso_or_none(getattr(coordinator, "last_success", None)),
            "last_failure": _iso_or_none(getattr(coordinator, "last_failure", None)),
            "consecutive_failures": getattr(coordinator, "consecutive_failures", 0),
            "last_error": getattr(coordinator, "last_error", None),
        },
        "registers": register_data,
    }
