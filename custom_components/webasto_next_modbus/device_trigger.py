"""Device triggers for the Webasto Next Modbus integration."""

from __future__ import annotations

from typing import Any, Protocol

import voluptuous as vol
from homeassistant.components.device_automation.exceptions import (
    InvalidDeviceAutomationConfig,
)
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_PLATFORM,
    CONF_TYPE,
)
from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

TRIGGER_CHARGING_STARTED = "charging_started"
TRIGGER_CHARGING_STOPPED = "charging_stopped"
TRIGGER_CONNECTION_LOST = "connection_lost"
TRIGGER_CONNECTION_RESTORED = "connection_restored"
TRIGGER_KEEPALIVE_SENT = "keepalive_sent"
TRIGGER_CABLE_CONNECTED = "cable_connected"
TRIGGER_CABLE_DISCONNECTED = "cable_disconnected"
TRIGGER_FAULT_OCCURRED = "fault_occurred"

TRIGGER_TYPES: tuple[str, ...] = (
    TRIGGER_CHARGING_STARTED,
    TRIGGER_CHARGING_STOPPED,
    TRIGGER_CONNECTION_LOST,
    TRIGGER_CONNECTION_RESTORED,
    TRIGGER_KEEPALIVE_SENT,
    TRIGGER_CABLE_CONNECTED,
    TRIGGER_CABLE_DISCONNECTED,
    TRIGGER_FAULT_OCCURRED,
)

TRIGGER_SCHEMA = cv.TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Optional(CONF_DOMAIN): vol.In([DOMAIN]),
        vol.Required(CONF_DEVICE_ID): cv.string,
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
    }
)

SIGNAL_DEVICE_TRIGGER = "webasto_next_modbus_device_trigger_{device_slug}"


class _DeviceWithIdentifiers(Protocol):
    """Registry entry exposing identifiers.

    ``DeviceRegistry.async_get`` returns ``DeviceEntry | ChildDeviceEntry`` since
    HA 2026.8; both carry ``identifiers``. A protocol keeps this working with
    releases that predate ``ChildDeviceEntry``.
    """

    @property
    def identifiers(self) -> set[tuple[str, str]]:
        """Return the device identifiers."""


def _get_device_slug(device_entry: _DeviceWithIdentifiers | None) -> str | None:
    if not device_entry:
        return None
    for domain, slug in device_entry.identifiers:
        if domain == DOMAIN:
            return slug
    return None


async def async_get_triggers(
    hass: HomeAssistant,
    device_id: str,
) -> list[dict[str, Any]]:
    """Return a list of device triggers for the given device."""

    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get(device_id)
    device_slug = _get_device_slug(device_entry)
    if not device_slug:
        return []

    return [
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: trigger_type,
        }
        for trigger_type in TRIGGER_TYPES
    ]


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a device trigger."""

    config = TRIGGER_SCHEMA(config)
    device_id = config[CONF_DEVICE_ID]
    trigger_type = config[CONF_TYPE]

    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get(device_id)
    device_slug = _get_device_slug(device_entry)
    if not device_slug:
        raise InvalidDeviceAutomationConfig(
            f"Device {device_id} is not a Webasto Next Modbus device"
        )

    job = HassJob(action, f"webasto_next_modbus device trigger {trigger_type}")
    trigger_data = trigger_info["trigger_data"]

    @callback
    def _handle_trigger(event_type: str, extra: dict[str, Any] | None) -> None:
        if event_type != trigger_type:
            return

        # Automations read the trigger variables from run_variables["trigger"];
        # trigger_data carries the automation's id/idx/alias for that trigger.
        payload: dict[str, Any] = {
            **trigger_data,
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: trigger_type,
            "description": f"Webasto Next {trigger_type.replace('_', ' ')}",
        }
        if extra:
            payload.update(extra)
        hass.async_run_hass_job(job, {"trigger": payload})

    return async_dispatcher_connect(
        hass,
        SIGNAL_DEVICE_TRIGGER.format(device_slug=device_slug),
        _handle_trigger,
    )


def async_fire_device_trigger(
    hass: HomeAssistant,
    device_slug: str,
    trigger_type: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Fire a device trigger for the given device slug."""

    if trigger_type not in TRIGGER_TYPES:
        return

    async_dispatcher_send(
        hass,
        SIGNAL_DEVICE_TRIGGER.format(device_slug=device_slug),
        trigger_type,
        extra or {},
    )
