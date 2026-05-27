"""Webasto Next Modbus integration entry points."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import cast

import voluptuous as vol
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_MODEL,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_UNIT_ID,
    CONF_VARIANT,
    DEFAULT_MODEL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VARIANT,
    DEVICE_NAME,
    DOMAIN,
    KEEPALIVE_TRIGGER_VALUE,
    MAX_RETRY_ATTEMPTS,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    MODEL_NEXT,
    RETRY_BACKOFF_SECONDS,
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
from .coordinator import WebastoDataCoordinator
from .device_trigger import TRIGGER_KEEPALIVE_SENT, async_fire_device_trigger
from .hub import ModbusBridge, WebastoModbusError

_LOGGER = logging.getLogger(__name__)

_INTEGRATION_PATH = Path(__file__).resolve().parent
_INTEGRATION_PATH_LOGGED = False
_SERVICES_REGISTERED = False

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.SWITCH,
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
    configured_name = entry.data.get(CONF_NAME)
    device_name = configured_name or entry.title or DEVICE_NAME

    updated_data = dict(entry.data)
    if CONF_VARIANT not in updated_data:
        updated_data[CONF_VARIANT] = variant
    if CONF_MODEL not in updated_data:
        updated_data[CONF_MODEL] = model
    if configured_name != updated_data.get(CONF_NAME):
        # Keep stored name in sync with data payload; remove empty values.
        if configured_name:
            updated_data[CONF_NAME] = configured_name
        elif CONF_NAME in updated_data:
            updated_data.pop(CONF_NAME)
    if updated_data != entry.data:
        hass.config_entries.async_update_entry(entry, data=updated_data)

    bridge = ModbusBridge(
        host=host,
        port=port,
        unit_id=unit_id,
        registers=get_readable_registers(model),
    )

    notification_id = f"{DOMAIN}_setup_{entry.entry_id}"

    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            await bridge.async_connect()
            persistent_notification.async_dismiss(hass, notification_id)
            break
        except WebastoModbusError as err:
            msg = f"Verbindungsversuch {attempt}/{MAX_RETRY_ATTEMPTS} fehlgeschlagen: {err}"
            _LOGGER.warning(msg)

            if attempt == MAX_RETRY_ATTEMPTS:
                persistent_notification.async_dismiss(hass, notification_id)
                raise ConfigEntryNotReady(msg) from err

            persistent_notification.async_create(
                hass,
                f"{msg}\nNächster Versuch in wenigen Sekunden...",
                title="Webasto Next Verbindung",
                notification_id=notification_id,
            )
            await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)

    update_interval = timedelta(seconds=_clamp(scan_interval, MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL))
    coordinator = WebastoDataCoordinator(
        hass,
        entry.entry_id,
        bridge,
        update_interval,
        device_slug,
        config_entry=entry,
        device_model_name=get_model_display_name(model),
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        # Don't leave the Modbus socket open on a failed setup: these wallboxes
        # typically accept only one Modbus TCP connection, so a stale socket
        # makes the automatic retry fail with "connection refused".
        await bridge.async_close()
        raise

    # Initialize REST client if configured
    await coordinator.async_setup_rest_client()

    # Start the Life Bit loop after coordinator is ready
    await bridge.start_life_bit_loop()

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

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    return True


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
        await runtime.coordinator.async_shutdown_rest_client()
        await runtime.bridge.stop_life_bit_loop()
        await runtime.bridge.async_close()
        _LOGGER.debug("Connection closed for entry %s", entry.entry_id)

    _LOGGER.info("Config entry %s unloaded successfully", entry.entry_id)
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: WebastoConfigEntry) -> None:
    """Reload entry when options change."""

    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
    """Register integration-wide services (idempotent)."""

    global _SERVICES_REGISTERED
    if _SERVICES_REGISTERED:
        return

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CURRENT,
        _async_service_set_current,
        schema=vol.Schema(
            {
                vol.Optional("config_entry_id"): cv.string,
                vol.Required("amps"): vol.All(int, vol.Range(min=0, max=32)),
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_FAILSAFE,
        _async_service_set_failsafe,
        schema=vol.Schema(
            {
                vol.Optional("config_entry_id"): cv.string,
                vol.Required("amps"): vol.All(int, vol.Range(min=6, max=32)),
                vol.Optional("timeout_s"): vol.All(int, vol.Range(min=6, max=120)),
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_KEEPALIVE,
        _async_service_send_keepalive,
        schema=vol.Schema({vol.Optional("config_entry_id"): cv.string}),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_SESSION,
        _async_service_start_session,
        schema=vol.Schema({vol.Optional("config_entry_id"): cv.string}),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_SESSION,
        _async_service_stop_session,
        schema=vol.Schema({vol.Optional("config_entry_id"): cv.string}),
    )

    # REST API services
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_LED_BRIGHTNESS,
        _async_service_set_led_brightness,
        schema=vol.Schema(
            {
                vol.Optional("config_entry_id"): cv.string,
                vol.Required("brightness"): vol.All(int, vol.Range(min=0, max=100)),
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_FREE_CHARGING,
        _async_service_set_free_charging,
        schema=vol.Schema(
            {
                vol.Optional("config_entry_id"): cv.string,
                vol.Required("enabled"): bool,
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_RESTART_WALLBOX,
        _async_service_restart_wallbox,
        schema=vol.Schema({vol.Optional("config_entry_id"): cv.string}),
    )

    _SERVICES_REGISTERED = True


def _resolve_runtime(hass: HomeAssistant, call: ServiceCall) -> RuntimeData:
    """Resolve runtime data for service handlers.

    If multiple entries are configured, require the caller to specify
    `config_entry_id`. Otherwise the first entry is used implicitly.
    """

    entries = [
        entry
        for entry in hass.config_entries.async_loaded_entries(DOMAIN)
        if isinstance(getattr(entry, "runtime_data", None), RuntimeData)
    ]
    if not entries:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_configured")

    if len(entries) == 1:
        return cast(RuntimeData, entries[0].runtime_data)

    entry_id = call.data.get("config_entry_id")
    if entry_id:
        for entry in entries:
            if entry.entry_id == entry_id:
                return cast(RuntimeData, entry.runtime_data)

    raise ServiceValidationError(translation_domain=DOMAIN, translation_key="multiple_wallboxes")


def _require_session_command_support(runtime: RuntimeData) -> None:
    """Raise if the configured model has no start/stop-session command register."""

    if runtime.model != MODEL_NEXT:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="session_command_unsupported",
        )


async def _async_service_set_current(call: ServiceCall) -> None:
    """Handle service to set the dynamic charging current."""

    runtime = _resolve_runtime(call.hass, call)
    register = get_register("set_current_a")
    amps = int(call.data["amps"])
    max_allowed = min(runtime.max_current, register.max_value or runtime.max_current)
    value = int(_clamp(amps, register.min_value or 0, max_allowed))
    try:
        await runtime.bridge.async_write_register(register, value)
    except WebastoModbusError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="write_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    async_dispatcher_send(
        call.hass,
        SIGNAL_REGISTER_WRITTEN,
        runtime.device_slug,
        register.key,
        value,
    )
    await runtime.coordinator.async_request_refresh()


async def _async_service_set_failsafe(call: ServiceCall) -> None:
    """Handle service to configure fail-safe parameters."""

    runtime = _resolve_runtime(call.hass, call)
    amps_register = get_register("failsafe_current_a")
    amps = int(call.data["amps"])
    max_allowed = min(runtime.max_current, amps_register.max_value or runtime.max_current)
    amps_value = int(_clamp(amps, amps_register.min_value or 6, max_allowed))
    try:
        await runtime.bridge.async_write_register(amps_register, amps_value)
    except WebastoModbusError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="write_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    async_dispatcher_send(
        call.hass,
        SIGNAL_REGISTER_WRITTEN,
        runtime.device_slug,
        amps_register.key,
        amps_value,
    )

    timeout_value: int | None = None
    if "timeout_s" in call.data:
        timeout_register = get_register("failsafe_timeout_s")
        timeout = int(call.data["timeout_s"])
        timeout_value = int(
            _clamp(timeout, timeout_register.min_value or 6, timeout_register.max_value or 120)
        )
        try:
            await runtime.bridge.async_write_register(timeout_register, timeout_value)
        except WebastoModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        async_dispatcher_send(
            call.hass,
            SIGNAL_REGISTER_WRITTEN,
            runtime.device_slug,
            timeout_register.key,
            timeout_value,
        )

    await runtime.coordinator.async_request_refresh()


async def _async_service_send_keepalive(call: ServiceCall) -> None:
    """Handle service to send an explicit keep-alive frame."""

    runtime = _resolve_runtime(call.hass, call)
    register = get_register("send_keepalive")
    try:
        await runtime.bridge.async_write_register(register, KEEPALIVE_TRIGGER_VALUE)
    except WebastoModbusError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="write_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    async_fire_device_trigger(
        call.hass,
        runtime.device_slug,
        TRIGGER_KEEPALIVE_SENT,
        {"source": "service"},
    )
    await runtime.coordinator.async_request_refresh()


async def _async_service_start_session(call: ServiceCall) -> None:
    """Handle service to start a charging session explicitly."""

    runtime = _resolve_runtime(call.hass, call)
    _require_session_command_support(runtime)
    register = get_register("session_command")
    try:
        await runtime.bridge.async_write_register(register, SESSION_COMMAND_START_VALUE)
    except WebastoModbusError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="write_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    await runtime.coordinator.async_request_refresh()


async def _async_service_stop_session(call: ServiceCall) -> None:
    """Handle service to stop the active charging session."""

    runtime = _resolve_runtime(call.hass, call)
    _require_session_command_support(runtime)
    register = get_register("session_command")
    try:
        await runtime.bridge.async_write_register(register, SESSION_COMMAND_STOP_VALUE)
    except WebastoModbusError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="write_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    await runtime.coordinator.async_request_refresh()


async def _async_service_set_led_brightness(call: ServiceCall) -> None:
    """Handle service to set LED brightness via REST API."""
    from .rest_client import RestClientError

    runtime = _resolve_runtime(call.hass, call)
    if not runtime.coordinator.rest_enabled:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="rest_not_enabled")

    brightness = int(call.data["brightness"])
    rest_client = runtime.coordinator.rest_client
    if rest_client is None:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="rest_not_connected")

    try:
        await rest_client.set_led_brightness(brightness)
    except RestClientError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="set_led_brightness_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    await runtime.coordinator.async_refresh_rest_data()


async def _async_service_set_free_charging(call: ServiceCall) -> None:
    """Handle service to enable/disable free charging via REST API."""
    from .rest_client import RestClientError

    runtime = _resolve_runtime(call.hass, call)
    if not runtime.coordinator.rest_enabled:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="rest_not_enabled")

    enabled = bool(call.data["enabled"])
    rest_client = runtime.coordinator.rest_client
    if rest_client is None:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="rest_not_connected")

    try:
        await rest_client.set_free_charging(enabled)
    except RestClientError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="set_free_charging_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    await runtime.coordinator.async_refresh_rest_data()


async def _async_service_restart_wallbox(call: ServiceCall) -> None:
    """Handle service to restart the wallbox via REST API."""
    from .rest_client import RestClientError

    runtime = _resolve_runtime(call.hass, call)
    if not runtime.coordinator.rest_enabled:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="rest_not_enabled")

    rest_client = runtime.coordinator.rest_client
    if rest_client is None:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="rest_not_connected")

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
