"""Data update coordinator for Webasto Next Modbus integration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
	DOMAIN,
	FAILURE_NOTIFICATION_THRESHOLD,
	FAILURE_NOTIFICATION_TITLE,
)
from .device_trigger import (
	TRIGGER_CHARGING_STARTED,
	TRIGGER_CHARGING_STOPPED,
	TRIGGER_CONNECTION_LOST,
	TRIGGER_CONNECTION_RESTORED,
	async_fire_device_trigger,
)
from .hub import ModbusBridge, WebastoModbusError

_LOGGER = logging.getLogger(__name__)


class WebastoDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
	"""Coordinate Modbus polling and expose decoded values."""

	def __init__(
		self,
		hass: HomeAssistant,
		entry_id: str,
		bridge: ModbusBridge,
		update_interval: timedelta,
		device_slug: str,
		config_entry: ConfigEntry | None = None,
	) -> None:
		self._bridge = bridge
		self._device_slug = device_slug
		self.entry_id = entry_id
		self.consecutive_failures = 0
		self.last_success: datetime | None = None
		self.last_failure: datetime | None = None
		self.last_error: str | None = None
		self._connection_online = True
		self._notification_id = f"{DOMAIN}_connection_{entry_id}"
		super().__init__(
			hass,
			_LOGGER,
			name="Webasto Next Modbus",
			config_entry=config_entry,
			update_interval=update_interval,
		)

	async def _async_update_data(self) -> dict[str, Any]:
		previous_data: dict[str, Any] | None = self.data if isinstance(self.data, dict) else None
		try:
			data = await self._bridge.async_read_data()
		except WebastoModbusError as err:
			self.consecutive_failures += 1
			self.last_failure = datetime.now(UTC)
			self.last_error = str(err)
			if self._connection_online:
				self._connection_online = False
				async_fire_device_trigger(
					self.hass,
					self._device_slug,
					TRIGGER_CONNECTION_LOST,
					{"error": str(err)},
				)
			if self.consecutive_failures >= FAILURE_NOTIFICATION_THRESHOLD:
				self._ensure_failure_notification()
			raise UpdateFailed(str(err)) from err
		else:
			restored = not self._connection_online
			self.consecutive_failures = 0
			self.last_success = datetime.now(UTC)
			self.last_error = None
			self._dismiss_failure_notification()
			if restored:
				self._connection_online = True
				async_fire_device_trigger(
					self.hass,
					self._device_slug,
					TRIGGER_CONNECTION_RESTORED,
					{"timestamp": self.last_success.isoformat()},
				)
			self._emit_charging_triggers(previous_data, data)
			return data

	def _emit_charging_triggers(
		self,
		previous: dict[str, Any] | None,
		current: dict[str, Any],
	) -> None:
		if not previous:
			return

		previous_state_raw = previous.get("charging_state")
		current_state_raw = current.get("charging_state")
		if previous_state_raw is None or current_state_raw is None:
			return

		try:
			previous_state = int(previous_state_raw)
			current_state = int(current_state_raw)
		except (TypeError, ValueError):
			return

		if previous_state == current_state:
			return

		extra = {
			"charging_state": current_state,
			"previous_state": previous_state,
			"charge_point_state": current.get("charge_point_state"),
		}

		if current_state == 1:
			async_fire_device_trigger(
				self.hass,
				self._device_slug,
				TRIGGER_CHARGING_STARTED,
				extra,
			)
		elif previous_state == 1 and current_state == 0:
			async_fire_device_trigger(
				self.hass,
				self._device_slug,
				TRIGGER_CHARGING_STOPPED,
				extra,
			)

	def _ensure_failure_notification(self) -> None:
		message = (
			"Home Assistant konnte die Verbindung zur Webasto Next Wallbox "
			f"({self._bridge.endpoint}) wiederholt nicht herstellen. Prüfe Netzwerk, "
			"Stromversorgung und Zugangsdaten."
		)
		if self.last_error:
			message += f"\nLetzte Fehlermeldung: {self.last_error}"
		persistent_notification.async_create(
			self.hass,
			message,
			FAILURE_NOTIFICATION_TITLE,
			self._notification_id,
		)

	def _dismiss_failure_notification(self) -> None:
		persistent_notification.async_dismiss(self.hass, self._notification_id)
