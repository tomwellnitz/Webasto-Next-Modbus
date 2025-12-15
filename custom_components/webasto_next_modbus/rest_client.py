"""Async REST API client for Webasto Next / Ampure Unite wallboxes."""

from __future__ import annotations

import asyncio
import logging
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

import aiohttp

if TYPE_CHECKING:
    from collections.abc import Mapping

_LOGGER = logging.getLogger(__name__)

# API Configuration
DEFAULT_TIMEOUT: Final = 30
TOKEN_REFRESH_MARGIN: Final = timedelta(minutes=5)
MAX_RETRY_ATTEMPTS: Final = 3
RETRY_BACKOFF_SECONDS: Final = 1.0


class RestClientError(Exception):
    """Base exception for REST client errors."""


class AuthenticationError(RestClientError):
    """Raised when authentication fails."""


class ConnectionError(RestClientError):  # noqa: A001
    """Raised when connection to wallbox fails."""


class HttpRequestError(RestClientError):
    """Raised when the REST API returns an HTTP error status."""

    def __init__(self, status: int, path: str, body: str) -> None:
        super().__init__(f"Request failed: {status} - {body}")
        self.status = status
        self.path = path
        self.body = body


@dataclass(frozen=True, slots=True)
class RestData:
    """Data retrieved from the REST API."""

    # Firmware versions
    comboard_sw_version: str | None = None
    powerboard_sw_version: str | None = None
    comboard_hw_version: str | None = None
    powerboard_hw_version: str | None = None

    # Network info
    mac_address_ethernet: str | None = None
    mac_address_wifi: str | None = None
    ip_address: str | None = None

    # Statistics
    plug_cycles: int | None = None
    error_counter: int | None = None
    total_charging_sessions: int | None = None

    # Settings
    led_brightness: int | None = None

    # Authorization
    free_charging_enabled: bool | None = None
    free_charging_tag_id: str | None = None

    # System status
    signal_voltage_l1: float | None = None
    signal_voltage_l2: float | None = None
    signal_voltage_l3: float | None = None
    active_errors: list[str] | None = None


class RestClient:
    """Async REST API client for Webasto Next wallbox.

    This client provides access to features not available via Modbus:
    - LED brightness control
    - Firmware/hardware versions
    - MAC addresses and network info
    - Diagnostic counters (plug cycles, errors)
    - System restart
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        *,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the REST client.

        Args:
            host: Wallbox IP address or hostname.
            username: Web interface username (usually "admin").
            password: Web interface password.
            timeout: Request timeout in seconds.
        """
        self._host = host
        self._username = username
        self._password = password
        self._timeout = timeout
        self._base_url = f"https://{host}/api"

        self._session: aiohttp.ClientSession | None = None
        self._token: str | None = None
        self._token_expires: datetime | None = None
        self._ssl_context: ssl.SSLContext | None = None

    @property
    def is_connected(self) -> bool:
        """Return True if we have a valid token."""
        if self._token is None or self._token_expires is None:
            return False
        return datetime.now(UTC) < self._token_expires - TOKEN_REFRESH_MARGIN

    async def connect(self) -> None:
        """Establish connection and authenticate.

        Raises:
            AuthenticationError: If login fails.
            ConnectionError: If connection to wallbox fails.
        """
        await self._ensure_session()
        await self._login()

    async def disconnect(self) -> None:
        """Close the session."""
        if self._session is not None:
            await self._session.close()
            self._session = None
        self._token = None
        self._token_expires = None

    async def get_data(self) -> RestData:
        """Fetch all REST API data.

        Returns:
            RestData with firmware versions, network info, and statistics.

        Raises:
            RestClientError: If fetching data fails.
        """
        await self._ensure_token()

        values: dict[str, Any] = {}

        # Fetch system section
        try:
            system_fields = await self._get_section("system")
            self._parse_system_fields(system_fields, values)
        except Exception as err:
            _LOGGER.warning("Failed to fetch system section: %s", err)

        # Fetch auth section for free charging
        try:
            auth_fields = await self._get_section("auth")
            self._parse_auth_fields(auth_fields, values)
        except Exception as err:
            _LOGGER.warning("Failed to fetch auth section: %s", err)

        # Fetch current errors
        try:
            errors = await self._get_current_errors()
            values["active_errors"] = errors
        except Exception as err:
            _LOGGER.warning("Failed to fetch current errors: %s", err)

        return RestData(**values)

    async def set_led_brightness(self, brightness: int) -> None:
        """Set LED brightness.

        Args:
            brightness: Brightness value 0-100.

        Raises:
            ValueError: If brightness is out of range.
            RestClientError: If the request fails.
        """
        if not 0 <= brightness <= 100:
            msg = f"Brightness must be 0-100, got {brightness}"
            raise ValueError(msg)

        await self._ensure_token()
        await self._update_config(
            [
                {
                    "fieldKey": "led-brightness",
                    "value": brightness,
                    "configurationFieldUpdateType": "number-configuration-field-update",
                }
            ]
        )

    async def set_free_charging(self, enabled: bool) -> None:
        """Enable or disable free charging mode.

        Args:
            enabled: True to enable, False to disable.

        Raises:
            RestClientError: If the request fails.
        """
        await self._ensure_token()
        await self._update_config(
            [
                {
                    "fieldKey": "free-charging",
                    "value": enabled,
                    "configurationFieldUpdateType": "boolean-configuration-field-update",
                }
            ]
        )

    async def set_free_charging_tag_id(self, tag_id: str) -> None:
        """Set the tag ID alias for free charging.

        Args:
            tag_id: The new tag ID alias.

        Raises:
            RestClientError: If the request fails.
        """
        await self._ensure_token()
        await self._update_config(
            [
                {
                    "fieldKey": "free-charging-alais",
                    "value": tag_id,
                    "configurationFieldUpdateType": "simple-string-configuration-field-update",
                }
            ]
        )

    async def restart_system(self) -> None:
        """Trigger a system restart.

        Raises:
            RestClientError: If the request fails.
        """
        await self._ensure_token()
        await self._post("/custom-actions/restart-system")

    async def test_connection(self) -> bool:
        """Test if connection and authentication work.

        Returns:
            True if connection is successful.
        """
        try:
            await self.connect()
            return True
        except RestClientError:
            return False
        finally:
            # Don't disconnect - keep session for later use
            pass

    # -------------------------------------------------------------------------
    # Private methods
    # -------------------------------------------------------------------------

    async def _ensure_session(self) -> None:
        """Create aiohttp session if not exists."""
        if self._session is None or self._session.closed:
            # Create SSL context that doesn't verify certificates
            # (wallbox uses self-signed cert)
            self._ssl_context = ssl.create_default_context()
            self._ssl_context.check_hostname = False
            self._ssl_context.verify_mode = ssl.CERT_NONE

            connector = aiohttp.TCPConnector(ssl=self._ssl_context)
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
            )

    async def _ensure_token(self) -> None:
        """Ensure we have a valid token, refresh if needed."""
        if not self.is_connected:
            await self._login()

    async def _login(self) -> None:
        """Authenticate and obtain JWT token."""
        if self._session is None:
            await self._ensure_session()

        assert self._session is not None  # noqa: S101

        url = f"{self._base_url}/login"
        payload = {"username": self._username, "password": self._password}

        try:
            async with self._session.post(url, json=payload) as resp:
                if resp.status == 401:
                    msg = "Invalid username or password"
                    raise AuthenticationError(msg)
                if resp.status != 200:
                    msg = f"Login failed with status {resp.status}"
                    raise AuthenticationError(msg)

                data = await resp.json()
                self._token = data.get("access_token")
                if not self._token:
                    msg = "No access_token in response"
                    raise AuthenticationError(msg)

                # JWT tokens typically expire after some time
                # We'll assume 1 hour if not specified
                self._token_expires = datetime.now(UTC) + timedelta(hours=1)
                _LOGGER.debug("Successfully authenticated to REST API")

        except aiohttp.ClientError as err:
            msg = f"Connection to {self._host} failed: {err}"
            raise ConnectionError(msg) from err

    async def _get(self, path: str) -> Any:
        """Make authenticated GET request."""
        return await self._request("GET", path)

    async def _post(
        self,
        path: str,
        json: Mapping[str, Any] | list[dict[str, Any]] | None = None,
    ) -> Any:
        """Make authenticated POST request."""
        return await self._request("POST", path, json=json)

    async def _put(
        self,
        path: str,
        json: Mapping[str, Any] | list[dict[str, Any]] | None = None,
    ) -> Any:
        """Make authenticated PUT request."""
        return await self._request("PUT", path, json=json)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | list[dict[str, Any]] | None = None,
    ) -> Any:
        """Make authenticated request with retry logic."""
        if self._session is None:
            await self._ensure_session()

        assert self._session is not None  # noqa: S101
        assert self._token is not None  # noqa: S101

        url = f"{self._base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            try:
                await self._ensure_session()
                assert self._session is not None  # noqa: S101

                async with self._session.request(method, url, headers=headers, json=json) as resp:
                    if resp.status == 401:
                        # Token expired, re-authenticate
                        _LOGGER.debug("Token expired (401), re-authenticating...")
                        await self._login()
                        headers["Authorization"] = f"Bearer {self._token}"
                        continue
                    if resp.status == 404:
                        msg = f"Endpoint not found: {path}"
                        raise RestClientError(msg)
                    if resp.status >= 400:
                        text = await resp.text()
                        raise HttpRequestError(resp.status, path, text)

                    if resp.content_type == "application/json":
                        return await resp.json()
                    return await resp.text()

            except asyncio.CancelledError:
                raise
            except aiohttp.ClientError as err:
                last_error = err
                _LOGGER.warning(
                    "Attempt %s/%s to %s failed: %s",
                    attempt,
                    MAX_RETRY_ATTEMPTS,
                    f"{method} {path}",
                    err,
                )

                # Force session close to ensure fresh connection on retry
                if self._session and not self._session.closed:
                    await self._session.close()
                self._session = None

                if attempt == MAX_RETRY_ATTEMPTS:
                    break

                await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)

        msg = f"Request to {path} failed after {MAX_RETRY_ATTEMPTS} attempts"
        if last_error:
            raise RestClientError(msg) from last_error
        raise RestClientError(msg)

    async def _get_section(self, section: str) -> list[dict[str, Any]]:
        """Get configuration fields for a section."""
        result = await self._get(f"/sections/{section}")
        if not isinstance(result, list):
            return []
        return result

    async def _get_current_errors(self) -> list[str]:
        """Get list of current active errors."""
        result = await self._get("/current-errors")
        if not isinstance(result, list):
            return []
        # Extract error descriptions or codes
        errors = []
        for error in result:
            if isinstance(error, dict):
                desc = error.get("errorDescription") or error.get("errorCode", "Unknown")
                errors.append(str(desc))
            else:
                errors.append(str(error))
        return errors

    async def _update_config(self, updates: list[dict[str, Any]]) -> None:
        """Update configuration fields."""
        await self._post("/configuration-updates", json=updates)

    def _parse_system_fields(self, fields: list[dict[str, Any]], values: dict[str, Any]) -> None:
        """Parse system section fields into values dict."""
        for field in fields:
            key = field.get("fieldKey", "")
            value = field.get("value")

            if key == "comboard-sw-version":
                values["comboard_sw_version"] = value
            elif key == "powerboard-sw-version":
                values["powerboard_sw_version"] = value
            elif key == "comboard-hw-version":
                values["comboard_hw_version"] = value
            elif key == "powerboard-hw-version":
                values["powerboard_hw_version"] = value
            elif key == "MAC-Address Eth0":
                values["mac_address_ethernet"] = value
            elif key == "MAC-Address WiFi":
                values["mac_address_wifi"] = value
            elif key == "plug-cycles":
                values["plug_cycles"] = self._safe_int(value)
            elif key == "error-counter":
                values["error_counter"] = self._safe_int(value)
            elif key == "total-charging-sessions":
                values["total_charging_sessions"] = self._safe_int(value)
            elif key == "led-brightness":
                values["led_brightness"] = self._safe_int(value)
            elif key == "interfaces":
                values["ip_address"] = self._extract_ip(value)
            elif key == "signal-voltage":
                voltages = self._parse_signal_values(value)
                if voltages:
                    values["signal_voltage_l1"] = voltages.get("l1")
                    values["signal_voltage_l2"] = voltages.get("l2")
                    values["signal_voltage_l3"] = voltages.get("l3")

    def _parse_auth_fields(self, fields: list[dict[str, Any]], values: dict[str, Any]) -> None:
        """Parse auth section fields into values dict."""
        for field in fields:
            key = field.get("fieldKey", "")
            value = field.get("value")

            if key == "free-charging":
                values["free_charging_enabled"] = bool(value)
            elif key in ("free-charging-alais", "free-charging-alias"):
                values["free_charging_tag_id"] = value

    @staticmethod
    def _parse_signal_values(value: Any) -> dict[str, float] | None:
        """Parse signal voltages.

        The wallbox exposes signal voltages as a string in some firmwares/locales, e.g.
        "L1: 230.5V, L2: 231.0V, L3: 229.8V" or with decimal comma "230,5V".
        Some implementations may also return a mapping already.
        """

        if value is None:
            return None

        if isinstance(value, dict):
            result: dict[str, float] = {}
            for key in ("l1", "l2", "l3"):
                raw = value.get(key)
                if raw is None:
                    continue
                try:
                    result[key] = float(str(raw).replace(",", "."))
                except ValueError:
                    continue
            return result or None

        if not isinstance(value, str):
            return None

        text = value.strip()
        if not text:
            return None

        import re

        parsed_values: dict[str, float] = {}
        # Match patterns like "L1: 230.5", "L1:230,5V" or "L1 = 230.5 V"
        pattern = r"L([123])\s*[:=]\s*([0-9]+(?:[\.,][0-9]+)?)"
        matches = re.findall(pattern, text, re.IGNORECASE)

        for phase, voltage in matches:
            try:
                parsed_values[f"l{phase}"] = float(voltage.replace(",", "."))
            except ValueError:
                continue

        if parsed_values:
            return parsed_values

        # Fallback: Try comma-separated list "228 V, 227 V, 229 V"
        # Remove "V" and split by comma
        parts = [p.strip().replace("V", "").strip() for p in text.split(",")]
        if len(parts) == 3:
            try:
                parsed_values["l1"] = float(parts[0].replace(",", "."))
                parsed_values["l2"] = float(parts[1].replace(",", "."))
                parsed_values["l3"] = float(parts[2].replace(",", "."))
                return parsed_values
            except ValueError:
                pass

        return None

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        """Safely convert value to int."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _extract_ip(interfaces_str: str | None) -> str | None:
        """Extract primary IP address from interfaces string."""
        if not interfaces_str:
            return None

        # Look for IPv4 addresses (exclude 127.x.x.x and 172.20.x.x which is AP)
        import re

        pattern = r"inet\s+(\d+\.\d+\.\d+\.\d+)"
        matches = re.findall(pattern, interfaces_str)

        for ip in matches:
            if not ip.startswith("127.") and not ip.startswith("172.20."):
                return ip
        return matches[0] if matches else None
