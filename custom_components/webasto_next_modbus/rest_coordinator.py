"""Coordinator for the optional REST API of the wallbox web interface."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_REST_ENABLED,
    CONF_REST_PASSWORD,
    CONF_REST_USERNAME,
    DEFAULT_REST_USERNAME,
    DOMAIN,
    MODEL_NEXT,
    REST_FETCH_TIMEOUT,
    REST_SCAN_INTERVAL,
    REST_SYSTEM_SECTION_INTERVAL,
)
from .rest_client import AuthenticationError, RestClient, RestClientError, RestData

_LOGGER = logging.getLogger(__name__)


class WebastoRestCoordinator(DataUpdateCoordinator[RestData]):
    """Poll the REST API independently of the Modbus data.

    A slow or unreachable web interface therefore never delays the Modbus
    telemetry. Rejected credentials raise ``ConfigEntryAuthFailed``: Home
    Assistant starts the reauth flow and stops polling REST (no repeated
    logins with a wrong password), while Modbus keeps running.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: RestClient,
        device_slug: str,
        model: str = MODEL_NEXT,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Webasto Next REST API",
            config_entry=config_entry,
            update_interval=timedelta(seconds=REST_SCAN_INTERVAL),
        )
        self.client = client
        self.device_slug = device_slug
        self._model = model
        self._system_fetched_at: datetime | None = None
        self._force_system = False
        self._pushed_device_info: tuple[object, ...] | None = None
        self.initial_refresh: asyncio.Task[None] | None = None

    @callback
    def async_start_initial_refresh(self) -> None:
        """Fetch the REST data once in the background.

        Not a first refresh: the web interface must not delay the Modbus side.
        Until it answers the REST entities are unavailable; rejected
        credentials start the reauth flow.
        """
        assert self.config_entry is not None
        self.initial_refresh = self.config_entry.async_create_background_task(
            self.hass, self.async_refresh(), name=f"{DOMAIN} REST refresh"
        )

    async def _async_update_data(self) -> RestData:
        now = datetime.now(UTC)
        include_system = (
            self._force_system
            or self._system_fetched_at is None
            or now - self._system_fetched_at >= timedelta(seconds=REST_SYSTEM_SECTION_INTERVAL)
        )
        try:
            async with asyncio.timeout(REST_FETCH_TIMEOUT):
                data = await self.client.get_data(self.data, include_system=include_system)
        except AuthenticationError as err:
            # Stop polling until the reauth flow stores new credentials (which
            # reloads the entry): every poll would be another rejected login,
            # and the web interface locks accounts after repeated failures.
            # Adding an entity listener would otherwise reschedule polling.
            self.update_interval = None
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="rest_auth_failed",
            ) from err
        except (RestClientError, TimeoutError) as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="rest_update_failed",
                translation_placeholders={"error": str(err) or type(err).__name__},
            ) from err

        if include_system:
            self._system_fetched_at = now
            self._force_system = False
        self._async_update_device_registry(data)
        return data

    async def async_refresh_after_write(self) -> None:
        """Re-fetch everything right away so a write shows up immediately."""

        self._force_system = True
        await self.async_refresh()

    @callback
    def _async_update_device_registry(self, data: RestData) -> None:
        """Push firmware, hardware and MAC data to the device registry.

        Entities only hand their ``DeviceInfo`` to the registry when they are
        added, which happens before the first REST fetch, so the device page
        would never show these values otherwise.
        """
        if self.config_entry is None:
            return
        connections = {
            (dr.CONNECTION_NETWORK_MAC, dr.format_mac(mac))
            for mac in (data.mac_address_ethernet, data.mac_address_wifi)
            if mac
        }
        info = (data.comboard_sw_version, data.comboard_hw_version, frozenset(connections))
        if info == self._pushed_device_info or not any(
            (data.comboard_sw_version, data.comboard_hw_version, connections)
        ):
            return
        self._pushed_device_info = info
        kwargs: dict[str, object] = {}
        if data.comboard_sw_version:
            kwargs["sw_version"] = data.comboard_sw_version
        if data.comboard_hw_version:
            kwargs["hw_version"] = data.comboard_hw_version
        if connections:
            kwargs["connections"] = connections
        dr.async_get(self.hass).async_get_or_create(
            config_entry_id=self.config_entry.entry_id,
            identifiers={(DOMAIN, self.device_slug)},
            **kwargs,  # type: ignore[arg-type]
        )


def build_rest_client(hass: HomeAssistant, entry: ConfigEntry, model: str) -> RestClient | None:
    """Return a REST client for the entry, or ``None`` if REST isn't configured."""

    options = entry.options
    if not options.get(CONF_REST_ENABLED, False):
        return None
    password = options.get(CONF_REST_PASSWORD)
    if not password:
        _LOGGER.warning("REST API enabled but no password configured")
        return None
    # The wallbox serves a self-signed certificate, so the shared session
    # without SSL verification is used (never closed by the client).
    session = async_get_clientsession(hass, verify_ssl=False)
    return RestClient(
        entry.data[CONF_HOST],
        options.get(CONF_REST_USERNAME, DEFAULT_REST_USERNAME),
        password,
        session,
        model=model,
    )
