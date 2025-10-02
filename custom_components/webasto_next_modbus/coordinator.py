"""Data update coordinator for Webasto Next Modbus integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .hub import ModbusBridge, WebastoModbusError

_LOGGER = logging.getLogger(__name__)


class WebastoDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
	"""Coordinate Modbus polling and expose decoded values."""

	def __init__(
		self,
		hass: HomeAssistant,
		bridge: ModbusBridge,
		update_interval: timedelta,
	) -> None:
		self._bridge = bridge
		super().__init__(
			hass,
			_LOGGER,
			name="Webasto Next Modbus",
			update_interval=update_interval,
		)

	async def _async_update_data(self) -> dict[str, Any]:
		try:
			return await self._bridge.async_read_data()
		except WebastoModbusError as err:
			raise UpdateFailed(str(err)) from err
