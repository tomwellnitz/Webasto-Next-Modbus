"""Webasto Next Modbus integration entry points."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
	CONF_SCAN_INTERVAL,
	CONF_UNIT_ID,
	CONF_VARIANT,
	DEFAULT_SCAN_INTERVAL,
	DEFAULT_VARIANT,
	DOMAIN,
	KEEPALIVE_TRIGGER_VALUE,
	MAX_SCAN_INTERVAL,
	MIN_SCAN_INTERVAL,
	SERVICE_SEND_KEEPALIVE,
	SERVICE_SET_CURRENT,
	SERVICE_SET_FAILSAFE,
	SERVICE_START_SESSION,
	SERVICE_STOP_SESSION,
	SESSION_COMMAND_START_VALUE,
	SESSION_COMMAND_STOP_VALUE,
	build_device_slug,
	get_max_current_for_variant,
	get_register,
)
from .coordinator import WebastoDataCoordinator
from .device_trigger import TRIGGER_KEEPALIVE_SENT, async_fire_device_trigger
from .hub import ModbusBridge, WebastoModbusError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.BUTTON]


@dataclass(slots=True)
class RuntimeData:
	"""Hold runtime objects for a config entry."""

	bridge: ModbusBridge
	coordinator: WebastoDataCoordinator
	variant: str
	max_current: int
	device_slug: str


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
	"""Set up Webasto Next Modbus from a config entry."""

	host = entry.data[CONF_HOST]
	port = entry.data[CONF_PORT]
	unit_id = entry.data[CONF_UNIT_ID]
	scan_interval = entry.options.get(
		CONF_SCAN_INTERVAL,
		entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
	)

	variant = entry.options.get(CONF_VARIANT, entry.data.get(CONF_VARIANT, DEFAULT_VARIANT))
	max_current = get_max_current_for_variant(variant)
	device_slug = build_device_slug(host, unit_id)

	if CONF_VARIANT not in entry.data:
		updated_data = {**entry.data, CONF_VARIANT: variant}
		hass.config_entries.async_update_entry(entry, data=updated_data)

	bridge = ModbusBridge(host=host, port=port, unit_id=unit_id)

	try:
		await bridge.async_connect()
	except WebastoModbusError as err:
		raise ConfigEntryNotReady(str(err)) from err

	update_interval = timedelta(seconds=_clamp(scan_interval, MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL))
	coordinator = WebastoDataCoordinator(
		hass,
		entry.entry_id,
		bridge,
		update_interval,
		device_slug,
		config_entry=entry,
	)

	await coordinator.async_config_entry_first_refresh()

	domain_data = hass.data.setdefault(DOMAIN, {})
	domain_data[entry.entry_id] = RuntimeData(
		bridge=bridge,
		coordinator=coordinator,
		variant=variant,
		max_current=max_current,
		device_slug=device_slug,
	)

	await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

	entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

	_register_services(hass)
	return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
	"""Unload a config entry."""

	unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

	data = hass.data.get(DOMAIN, {})
	runtime: RuntimeData | None = data.pop(entry.entry_id, None)
	if runtime:
		await runtime.bridge.async_close()

	if unload_ok and not data:
		_unregister_services(hass)
		hass.data.pop(DOMAIN, None)

	return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
	"""Reload entry when options change."""

	await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
	"""Register integration-wide services (idempotent)."""

	if hass.data.setdefault(DOMAIN, {}).get("_services_registered"):
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

	hass.data[DOMAIN]["_services_registered"] = True


def _unregister_services(hass: HomeAssistant) -> None:
	"""Remove integration services when no entries remain."""

	if not hass.services.has_service(DOMAIN, SERVICE_SET_CURRENT):
		return

	hass.services.async_remove(DOMAIN, SERVICE_SET_CURRENT)
	hass.services.async_remove(DOMAIN, SERVICE_SET_FAILSAFE)
	hass.services.async_remove(DOMAIN, SERVICE_SEND_KEEPALIVE)
	hass.services.async_remove(DOMAIN, SERVICE_START_SESSION)
	hass.services.async_remove(DOMAIN, SERVICE_STOP_SESSION)


def _resolve_runtime(hass: HomeAssistant, call: ServiceCall) -> RuntimeData:
	"""Resolve runtime data for service handlers.

	If multiple entries are configured, require the caller to specify
	`config_entry_id`. Otherwise the first entry is used implicitly.
	"""

	entries = hass.data.get(DOMAIN)
	if not entries:
		raise ValueError("Webasto Next Modbus is not configured")

	runtime_data = {key: value for key, value in entries.items() if isinstance(value, RuntimeData)}
	if not runtime_data:
		raise ValueError("Runtime data not available")

	if len(runtime_data) == 1:
		return next(iter(runtime_data.values()))

	entry_id = call.data.get("config_entry_id")
	if entry_id and entry_id in runtime_data:
		return runtime_data[entry_id]

	raise ValueError("Multiple wallboxes configured – set config_entry_id in the service call")


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
		raise HomeAssistantError(f"Schreibvorgang fehlgeschlagen: {err}") from err
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
		raise HomeAssistantError(f"Schreibvorgang fehlgeschlagen: {err}") from err

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
			raise HomeAssistantError(f"Schreibvorgang fehlgeschlagen: {err}") from err

	await runtime.coordinator.async_request_refresh()


async def _async_service_send_keepalive(call: ServiceCall) -> None:
	"""Handle service to send an explicit keep-alive frame."""

	runtime = _resolve_runtime(call.hass, call)
	register = get_register("send_keepalive")
	try:
		await runtime.bridge.async_write_register(register, KEEPALIVE_TRIGGER_VALUE)
	except WebastoModbusError as err:
		raise HomeAssistantError(f"Schreibvorgang fehlgeschlagen: {err}") from err
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
	register = get_register("session_command")
	try:
		await runtime.bridge.async_write_register(register, SESSION_COMMAND_START_VALUE)
	except WebastoModbusError as err:
		raise HomeAssistantError(f"Schreibvorgang fehlgeschlagen: {err}") from err
	await runtime.coordinator.async_request_refresh()


async def _async_service_stop_session(call: ServiceCall) -> None:
	"""Handle service to stop the active charging session."""

	runtime = _resolve_runtime(call.hass, call)
	register = get_register("session_command")
	try:
		await runtime.bridge.async_write_register(register, SESSION_COMMAND_STOP_VALUE)
	except WebastoModbusError as err:
		raise HomeAssistantError(f"Schreibvorgang fehlgeschlagen: {err}") from err
	await runtime.coordinator.async_request_refresh()


def _clamp(value: float, minimum: float, maximum: float) -> float:
	"""Clamp a value to the provided bounds."""

	return max(minimum, min(maximum, value))
