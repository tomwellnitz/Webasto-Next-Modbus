"""Data update coordinator for Webasto Next Modbus integration."""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_REST_ENABLED,
    CONF_REST_PASSWORD,
    CONF_REST_USERNAME,
    DEFAULT_REST_USERNAME,
    DOMAIN,
    FAILURE_NOTIFICATION_THRESHOLD,
    FAILURE_NOTIFICATION_TITLE,
    MODEL,
    REST_SCAN_INTERVAL,
    REST_SETUP_RETRY_INTERVAL,
)
from .device_trigger import (
    TRIGGER_CABLE_CONNECTED,
    TRIGGER_CABLE_DISCONNECTED,
    TRIGGER_CHARGING_STARTED,
    TRIGGER_CHARGING_STOPPED,
    TRIGGER_CONNECTION_LOST,
    TRIGGER_CONNECTION_RESTORED,
    TRIGGER_FAULT_OCCURRED,
    async_fire_device_trigger,
)
from .hub import ModbusBridge, WebastoModbusError

if TYPE_CHECKING:
    from .rest_client import RestClient, RestData

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
        device_model_name: str = MODEL,
    ) -> None:
        self._bridge = bridge
        self._device_slug = device_slug
        self.device_model_name = device_model_name
        self.entry_id = entry_id
        self.consecutive_failures = 0
        self.last_success: datetime | None = None
        self.last_failure: datetime | None = None
        self.last_error: str | None = None
        self._connection_online = True
        self._notification_id = f"{DOMAIN}_connection_{entry_id}"

        # REST API client (optional)
        self._rest_client: RestClient | None = None
        self._rest_data: RestData | None = None
        self._rest_last_update: datetime | None = None
        self._rest_update_interval = timedelta(seconds=REST_SCAN_INTERVAL)
        # When the initial REST connect fails (e.g. the wallbox was still
        # booting), retry it from the data poll once this time has passed.
        self._rest_setup_retry_at: datetime | None = None
        self._rest_setup_retry_interval = timedelta(seconds=REST_SETUP_RETRY_INTERVAL)
        self._rest_fetch_warned = False

        super().__init__(
            hass,
            _LOGGER,
            name="Webasto Next Modbus",
            config_entry=config_entry,
            update_interval=update_interval,
        )

    async def async_setup_rest_client(self) -> None:
        """Initialize REST client if configured."""
        if self.config_entry is None:
            return

        options = self.config_entry.options
        if not options.get(CONF_REST_ENABLED, False):
            _LOGGER.debug("REST API not enabled")
            return

        username = options.get(CONF_REST_USERNAME, DEFAULT_REST_USERNAME)
        password = options.get(CONF_REST_PASSWORD)
        if not password:
            _LOGGER.warning("REST API enabled but no password configured")
            return

        # Import here to avoid circular imports
        from .rest_client import AuthenticationError, RestClient

        host = self._bridge.endpoint.split(":")[0]
        # Use Home Assistant's shared aiohttp session. The wallbox has a
        # self-signed certificate, so SSL verification must be disabled.
        session = async_get_clientsession(self.hass, verify_ssl=False)
        self._rest_client = RestClient(host, username, password, session)

        try:
            await self._rest_client.connect()
            _LOGGER.info("REST API client connected successfully")
            self._rest_setup_retry_at = None
        except AuthenticationError as err:
            _LOGGER.warning("REST API authentication failed: %s", err)
            with contextlib.suppress(Exception):
                await self._rest_client.disconnect()
            self._rest_client = None
            # Wrong credentials won't fix themselves by retrying — start a
            # reauth flow so the user can enter new ones. The Modbus side keeps
            # working regardless.
            self._rest_setup_retry_at = None
            if self.config_entry is not None:
                self.config_entry.async_start_reauth(self.hass)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Failed to connect REST API client: %s", err)
            with contextlib.suppress(Exception):
                await self._rest_client.disconnect()
            self._rest_client = None
            # The wallbox may just be booting; retry later from the data poll.
            self._rest_setup_retry_at = datetime.now(UTC) + self._rest_setup_retry_interval

    async def async_shutdown_rest_client(self) -> None:
        """Disconnect the REST client."""
        if self._rest_client is not None:
            await self._rest_client.disconnect()
            self._rest_client = None
            self._rest_data = None

    @property
    def rest_client(self) -> RestClient | None:
        """Return the REST client instance."""
        return self._rest_client

    @property
    def rest_enabled(self) -> bool:
        """Return True if REST client is active."""
        return self._rest_client is not None

    @property
    def rest_data(self) -> RestData | None:
        """Return cached REST data."""
        return self._rest_data

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
            self._emit_cable_triggers(previous_data, data)
            self._emit_fault_trigger(previous_data, data)

            # The Modbus side is up, so the wallbox is reachable: if a previous
            # REST setup failed, retry it now (throttled).
            if (
                self._rest_client is None
                and self._rest_setup_retry_at is not None
                and datetime.now(UTC) >= self._rest_setup_retry_at
            ):
                await self.async_setup_rest_client()

            # Fetch REST data if client is connected and interval elapsed
            await self._async_update_rest_data()

            return data

    async def async_refresh_rest_data(self) -> None:
        """Force an immediate REST data re-fetch (e.g. after a REST write).

        Regular REST polling is throttled to ``REST_SCAN_INTERVAL``; after we
        change something via REST we want the new value reflected right away
        instead of bouncing back to the stale cached value on the next Modbus
        poll.
        """
        if self._rest_client is None:
            return
        await self._async_update_rest_data(force=True)
        self.async_update_listeners()

    async def _async_update_rest_data(self, force: bool = False) -> None:
        """Fetch REST API data if enabled and the interval has passed."""
        if self._rest_client is None:
            return

        now = datetime.now(UTC)
        if (
            not force
            and self._rest_last_update is not None
            and now - self._rest_last_update < self._rest_update_interval
        ):
            return

        try:
            self._rest_data = await self._rest_client.get_data()
            self._rest_last_update = now
            _LOGGER.debug("REST data updated: %s", self._rest_data)
            if self._rest_fetch_warned:
                _LOGGER.info("REST data fetch recovered")
                self._rest_fetch_warned = False
        except Exception as err:  # noqa: BLE001
            # Keep stale data, don't clear it. Log once, then at debug.
            if not self._rest_fetch_warned:
                _LOGGER.warning("Failed to fetch REST data (will keep retrying): %s", err)
                self._rest_fetch_warned = True
            else:
                _LOGGER.debug("Still failing to fetch REST data: %s", err)

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
        except TypeError, ValueError:
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

    def _emit_cable_triggers(
        self,
        previous: dict[str, Any] | None,
        current: dict[str, Any],
    ) -> None:
        if not previous:
            return
        previous_raw = previous.get("cable_state")
        current_raw = current.get("cable_state")
        if previous_raw is None or current_raw is None:
            return
        try:
            previous_state = int(previous_raw)
            current_state = int(current_raw)
        except TypeError, ValueError:
            return
        if previous_state == current_state:
            return

        extra = {"cable_state": current_state, "previous_state": previous_state}
        if previous_state == 0 and current_state >= 1:
            async_fire_device_trigger(self.hass, self._device_slug, TRIGGER_CABLE_CONNECTED, extra)
        elif previous_state >= 1 and current_state == 0:
            async_fire_device_trigger(
                self.hass, self._device_slug, TRIGGER_CABLE_DISCONNECTED, extra
            )

    def _emit_fault_trigger(
        self,
        previous: dict[str, Any] | None,
        current: dict[str, Any],
    ) -> None:
        if not previous:
            return
        previous_raw = previous.get("fault_code")
        current_raw = current.get("fault_code")
        if previous_raw is None or current_raw is None:
            return
        try:
            previous_code = int(previous_raw)
            current_code = int(current_raw)
        except TypeError, ValueError:
            return

        # Fire only on the 0 -> non-zero edge so a persisting fault does not
        # re-fire on every poll.
        if previous_code == 0 and current_code != 0:
            async_fire_device_trigger(
                self.hass,
                self._device_slug,
                TRIGGER_FAULT_OCCURRED,
                {"fault_code": current_code},
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
