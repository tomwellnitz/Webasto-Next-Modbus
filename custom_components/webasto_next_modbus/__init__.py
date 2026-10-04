"""Webasto Next Modbus integration entry points."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_MODEL,
    CONF_NAME,
    CONF_REST_ENABLED,
    CONF_SCAN_INTERVAL,
    CONF_UNIT_ID,
    CONF_VARIANT,
    DEFAULT_MODEL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VARIANT,
    DEVICE_NAME,
    DOMAIN,
    KEEPALIVE_TRIGGER_VALUE,
    MAX_SCAN_INTERVAL,
    MIN_CHARGING_CURRENT,
    MIN_SCAN_INTERVAL,
    MODEL_NEXT,
    SERVICE_RESTART_WALLBOX,
    SERVICE_SEND_KEEPALIVE,
    SERVICE_SET_CURRENT,
    SERVICE_SET_FAILSAFE,
    SERVICE_SET_FREE_CHARGING,
    SERVICE_SET_LED_BRIGHTNESS,
    SERVICE_START_SESSION,
    SERVICE_STOP_SESSION,
    SESSION_COMMAND_START_VALUE,
    SESSION_COMMAND_STOP_VALUE,
    SIGNAL_REGISTER_WRITTEN,
    build_device_slug,
    get_max_current_for_variant,
    get_model_display_name,
    get_readable_registers,
    get_register,
    normalize_model,
)
from .coordinator import WebastoDataCoordinator, connection_issue_id
from .device_trigger import TRIGGER_KEEPALIVE_SENT, async_fire_device_trigger
from .hub import ModbusBridge, WebastoModbusError
from .rest_client import RestClient, RestClientError

_LOGGER = logging.getLogger(__name__)

_INTEGRATION_PATH = Path(__file__).resolve().parent
_INTEGRATION_PATH_LOGGED = False

# Config entries only; there is no YAML configuration.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Minor version 2: CONF_VARIANT / CONF_MODEL are always stored in entry.data
# and an empty CONF_NAME is not.
CONFIG_ENTRY_MINOR_VERSION = 2

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.TEXT,
]


@dataclass(slots=True)
class RuntimeData:
    """Hold runtime objects for a config entry."""

    bridge: ModbusBridge
    coordinator: WebastoDataCoordinator
    variant: str
    max_current: int
    device_slug: str
    device_name: str
    model: str = MODEL_NEXT


type WebastoConfigEntry = ConfigEntry[RuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register integration-wide service actions.

    Done here (not in async_setup_entry) so the actions exist and validate even
    before a config entry is set up, and persist for the lifetime of Home
    Assistant regardless of entry reloads.
    """

    _register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: WebastoConfigEntry) -> bool:
    """Set up Webasto Next Modbus from a config entry."""

    global _INTEGRATION_PATH_LOGGED
    if not _INTEGRATION_PATH_LOGGED:
        _LOGGER.debug("Webasto Next Modbus integration loaded from %s", _INTEGRATION_PATH)
        _INTEGRATION_PATH_LOGGED = True

    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    unit_id = entry.data[CONF_UNIT_ID]
    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    variant = entry.options.get(CONF_VARIANT, entry.data.get(CONF_VARIANT, DEFAULT_VARIANT))
    model = normalize_model(
        entry.options.get(CONF_MODEL, entry.data.get(CONF_MODEL, DEFAULT_MODEL))
    )
    max_current = get_max_current_for_variant(variant)
    device_slug = build_device_slug(host, unit_id)
    device_name = entry.data.get(CONF_NAME) or entry.title or DEVICE_NAME

    bridge = ModbusBridge(
        host=host,
        port=port,
        unit_id=unit_id,
        registers=get_readable_registers(model),
    )

    try:
        await bridge.async_connect()
    except WebastoModbusError as err:
        # Home Assistant retries the setup with its own backoff; the wallbox
        # is often just booting or its single Modbus slot is briefly taken.
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"error": str(err)},
        ) from err

    update_interval = timedelta(seconds=_clamp(scan_interval, MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL))
    coordinator = WebastoDataCoordinator(
        hass,
        entry.entry_id,
        bridge,
        update_interval,
        device_slug,
        config_entry=entry,
        device_model_name=get_model_display_name(model),
        model=model,
    )

    def _create_background_task(coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        return entry.async_create_background_task(
            hass, coro, name=f"{DOMAIN} life bit {entry.entry_id}"
        )

    try:
        await coordinator.async_config_entry_first_refresh()

        # Initialize REST client if configured
        await coordinator.async_setup_rest_client()

        # Start the Life Bit loop after coordinator is ready
        await bridge.start_life_bit_loop(_create_background_task)

        entry.runtime_data = RuntimeData(
            bridge=bridge,
            coordinator=coordinator,
            variant=variant,
            max_current=max_current,
            device_slug=device_slug,
            device_name=device_name,
            model=model,
        )

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        # Don't leave the Modbus socket open on a failed setup: these wallboxes
        # typically accept only one Modbus TCP connection, so a stale socket
        # makes the automatic retry fail with "connection refused".
        await _async_shutdown_runtime(coordinator, bridge)
        raise

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries to the current schema."""

    if entry.version > 1:
        # Downgraded from a future version we don't know how to read.
        return False

    if entry.minor_version < CONFIG_ENTRY_MINOR_VERSION:
        data = dict(entry.data)
        data.setdefault(CONF_VARIANT, entry.options.get(CONF_VARIANT, DEFAULT_VARIANT))
        data.setdefault(CONF_MODEL, normalize_model(entry.options.get(CONF_MODEL, DEFAULT_MODEL)))
        if not data.get(CONF_NAME):
            data.pop(CONF_NAME, None)
        hass.config_entries.async_update_entry(
            entry, data=data, minor_version=CONFIG_ENTRY_MINOR_VERSION
        )
        _LOGGER.debug(
            "Migrated config entry %s to version 1.%s", entry.entry_id, entry.minor_version
        )

    return True


async def _async_shutdown_runtime(
    coordinator: WebastoDataCoordinator, bridge: ModbusBridge
) -> None:
    """Stop background work and release the wallbox connection."""

    await coordinator.async_shutdown_rest_client()
    await bridge.stop_life_bit_loop()
    await bridge.async_close()


async def async_unload_entry(hass: HomeAssistant, entry: WebastoConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading config entry %s", entry.entry_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if not unload_ok:
        # If any platform failed to unload its entities, those entities may
        # still be active and would point at a closed bridge/coordinator if
        # we tore the runtime down here. Leave the runtime alive so the
        # entry stays consistent until Home Assistant retries / the user
        # restarts.
        _LOGGER.warning(
            "Config entry %s did not fully unload; keeping runtime alive",
            entry.entry_id,
        )
        return unload_ok

    runtime: RuntimeData | None = getattr(entry, "runtime_data", None)
    if runtime is not None:
        _LOGGER.debug("Stopping life bit loop and closing connection...")
        await _async_shutdown_runtime(runtime.coordinator, runtime.bridge)
        _LOGGER.debug("Connection closed for entry %s", entry.entry_id)

    # Nothing polls an unloaded entry any more, so its connection issue could
    # never clear itself; a reload recreates it if the problem persists.
    ir.async_delete_issue(hass, DOMAIN, connection_issue_id(entry.entry_id))

    _LOGGER.info("Config entry %s unloaded successfully", entry.entry_id)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean up when a config entry is deleted."""

    ir.async_delete_issue(hass, DOMAIN, connection_issue_id(entry.entry_id))


async def _async_reload_entry(hass: HomeAssistant, entry: WebastoConfigEntry) -> None:
    """Reload entry when options change."""

    await hass.config_entries.async_reload(entry.entry_id)


def _whole_number(value: Any) -> int:
    """Coerce a service value to int, accepting rendered templates like ``16.0``."""

    number = float(value)
    if not number.is_integer():
        raise vol.Invalid(f"expected a whole number, got {value}")
    return int(number)


_ENTRY_ID_SCHEMA: dict[Any, Any] = {vol.Optional("config_entry_id"): cv.string}

_SERVICE_SCHEMAS: dict[str, vol.Schema] = {
    SERVICE_SET_CURRENT: vol.Schema(
        {
            **_ENTRY_ID_SCHEMA,
            vol.Required("amps"): vol.All(_whole_number, vol.Range(min=0, max=32)),
        }
    ),
    SERVICE_SET_FAILSAFE: vol.Schema(
        {
            **_ENTRY_ID_SCHEMA,
            vol.Required("amps"): vol.All(_whole_number, vol.Range(min=6, max=32)),
            vol.Optional("timeout_s"): vol.All(_whole_number, vol.Range(min=6, max=120)),
        }
    ),
    SERVICE_SEND_KEEPALIVE: vol.Schema(_ENTRY_ID_SCHEMA),
    SERVICE_START_SESSION: vol.Schema(_ENTRY_ID_SCHEMA),
    SERVICE_STOP_SESSION: vol.Schema(_ENTRY_ID_SCHEMA),
    SERVICE_SET_LED_BRIGHTNESS: vol.Schema(
        {
            **_ENTRY_ID_SCHEMA,
            vol.Required("brightness"): vol.All(_whole_number, vol.Range(min=0, max=100)),
        }
    ),
    SERVICE_SET_FREE_CHARGING: vol.Schema(
        {
            **_ENTRY_ID_SCHEMA,
            vol.Required("enabled"): cv.boolean,
        }
    ),
    SERVICE_RESTART_WALLBOX: vol.Schema(_ENTRY_ID_SCHEMA),
}


def _register_services(hass: HomeAssistant) -> None:
    """Register integration-wide service actions (idempotent per hass)."""

    handlers = {
        SERVICE_SET_CURRENT: _async_service_set_current,
        SERVICE_SET_FAILSAFE: _async_service_set_failsafe,
        SERVICE_SEND_KEEPALIVE: _async_service_send_keepalive,
        SERVICE_START_SESSION: _async_service_start_session,
        SERVICE_STOP_SESSION: _async_service_stop_session,
        SERVICE_SET_LED_BRIGHTNESS: _async_service_set_led_brightness,
        SERVICE_SET_FREE_CHARGING: _async_service_set_free_charging,
        SERVICE_RESTART_WALLBOX: _async_service_restart_wallbox,
    }
    for service, handler in handlers.items():
        if hass.services.has_service(DOMAIN, service):
            continue
        hass.services.async_register(DOMAIN, service, handler, schema=_SERVICE_SCHEMAS[service])


def _resolve_runtime(hass: HomeAssistant, call: ServiceCall) -> RuntimeData:
    """Resolve the runtime data of the wallbox a service call targets.

    ``config_entry_id`` is optional while a single wallbox is configured; with
    several it is required. An explicitly given id must always match.
    """

    entries = [
        entry
        for entry in hass.config_entries.async_loaded_entries(DOMAIN)
        if isinstance(getattr(entry, "runtime_data", None), RuntimeData)
    ]
    if not entries:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_configured")

    entry_id = call.data.get("config_entry_id")
    if entry_id:
        for entry in entries:
            if entry.entry_id == entry_id:
                return cast(RuntimeData, entry.runtime_data)
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_found",
            translation_placeholders={"entry_id": str(entry_id)},
        )

    if len(entries) == 1:
        return cast(RuntimeData, entries[0].runtime_data)

    raise ServiceValidationError(translation_domain=DOMAIN, translation_key="multiple_wallboxes")


def _require_session_command_support(runtime: RuntimeData) -> None:
    """Raise if the configured model has no start/stop-session command register."""

    if runtime.model != MODEL_NEXT:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="session_command_unsupported",
        )


def _write_failed(err: WebastoModbusError) -> HomeAssistantError:
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="write_failed",
        translation_placeholders={"error": str(err)},
    )


async def _async_write(
    hass: HomeAssistant, runtime: RuntimeData, register_key: str, value: int
) -> None:
    """Write a register and tell the matching entity about the new value."""

    register = get_register(register_key)
    try:
        await runtime.bridge.async_write_register(register, value)
    except WebastoModbusError as err:
        raise _write_failed(err) from err
    async_dispatcher_send(hass, SIGNAL_REGISTER_WRITTEN, runtime.device_slug, register.key, value)


async def _async_service_set_current(call: ServiceCall) -> None:
    """Handle service to set the dynamic charging current."""

    runtime = _resolve_runtime(call.hass, call)
    amps = int(call.data["amps"])
    if 0 < amps < MIN_CHARGING_CURRENT:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="current_below_minimum",
            translation_placeholders={"minimum": str(MIN_CHARGING_CURRENT)},
        )
    # Above the variant's maximum the value is capped, like the number entity
    # does (an 11 kW unit given 32 A charges at 16 A).
    await _async_write(call.hass, runtime, "set_current_a", min(amps, runtime.max_current))
    await runtime.coordinator.async_request_refresh()


async def _async_service_set_failsafe(call: ServiceCall) -> None:
    """Handle service to configure fail-safe parameters."""

    runtime = _resolve_runtime(call.hass, call)
    amps = min(int(call.data["amps"]), runtime.max_current)
    await _async_write(call.hass, runtime, "failsafe_current_a", amps)
    if "timeout_s" in call.data:
        await _async_write(call.hass, runtime, "failsafe_timeout_s", int(call.data["timeout_s"]))
    await runtime.coordinator.async_request_refresh()


async def _async_service_send_keepalive(call: ServiceCall) -> None:
    """Handle service to send an explicit keep-alive frame."""

    runtime = _resolve_runtime(call.hass, call)
    register = get_register("send_keepalive")
    try:
        await runtime.bridge.async_write_register(register, KEEPALIVE_TRIGGER_VALUE)
    except WebastoModbusError as err:
        raise _write_failed(err) from err
    async_fire_device_trigger(
        call.hass,
        runtime.device_slug,
        TRIGGER_KEEPALIVE_SENT,
        {"source": "service"},
    )
    await runtime.coordinator.async_request_refresh()


async def _async_send_session_command(call: ServiceCall, value: int) -> None:
    runtime = _resolve_runtime(call.hass, call)
    _require_session_command_support(runtime)
    try:
        await runtime.bridge.async_send_session_command(value)
    except WebastoModbusError as err:
        raise _write_failed(err) from err
    await runtime.coordinator.async_request_refresh()


async def _async_service_start_session(call: ServiceCall) -> None:
    """Handle service to start a charging session explicitly."""

    await _async_send_session_command(call, SESSION_COMMAND_START_VALUE)


async def _async_service_stop_session(call: ServiceCall) -> None:
    """Handle service to stop the active charging session."""

    await _async_send_session_command(call, SESSION_COMMAND_STOP_VALUE)


def _require_rest_client(runtime: RuntimeData) -> RestClient:
    """Return the REST client, or raise a translated error explaining why not."""

    entry = runtime.coordinator.config_entry
    if entry is None or not entry.options.get(CONF_REST_ENABLED, False):
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="rest_not_enabled")
    rest_client = runtime.coordinator.rest_client
    if rest_client is None:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="rest_not_connected")
    return rest_client


async def _async_service_set_led_brightness(call: ServiceCall) -> None:
    """Handle service to set LED brightness via REST API."""

    runtime = _resolve_runtime(call.hass, call)
    rest_client = _require_rest_client(runtime)
    try:
        await rest_client.set_led_brightness(int(call.data["brightness"]))
    except RestClientError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="set_led_brightness_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    await runtime.coordinator.async_refresh_rest_data()


async def _async_service_set_free_charging(call: ServiceCall) -> None:
    """Handle service to enable/disable free charging via REST API."""

    runtime = _resolve_runtime(call.hass, call)
    rest_client = _require_rest_client(runtime)
    try:
        await rest_client.set_free_charging(bool(call.data["enabled"]))
    except RestClientError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="set_free_charging_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    await runtime.coordinator.async_refresh_rest_data()


async def _async_service_restart_wallbox(call: ServiceCall) -> None:
    """Handle service to restart the wallbox via REST API."""

    runtime = _resolve_runtime(call.hass, call)
    rest_client = _require_rest_client(runtime)
    try:
        await rest_client.restart_system()
    except RestClientError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="restart_failed",
            translation_placeholders={"error": str(err)},
        ) from err


def _clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp a value to the provided bounds."""

    return max(minimum, min(maximum, value))
