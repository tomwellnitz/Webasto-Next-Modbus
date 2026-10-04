"""Async REST API client for Webasto Next / Ampure Unite wallboxes."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

import aiohttp

from .const import (
    MODEL_NEXT,
    MODEL_UNITE,
    UNITE_LED_DIMMING_LEVELS,
    UNITE_RANDOMISED_DELAY_MAX,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

_LOGGER = logging.getLogger(__name__)

# API Configuration
# Per-request timeout. The wallbox web server answers within a second or two
# when it is up; a longer timeout only stretches outages.
DEFAULT_TIMEOUT: Final = 10
TOKEN_REFRESH_MARGIN: Final = timedelta(minutes=5)
# Used when the access token carries no readable ``exp`` claim.
DEFAULT_TOKEN_LIFETIME: Final = timedelta(hours=1)
# Idempotent GETs are retried once; POSTs (configuration updates, restart)
# are never retried, a duplicate restart or write is worse than a failure.
GET_ATTEMPTS: Final = 2
RETRY_BACKOFF_SECONDS: Final = 1.0
# After a failed login, callers within this many seconds get the same error
# instead of sending another login.
LOGIN_FAILURE_COOLDOWN: Final = 10.0
# Error bodies are kept on the exception, but only this much ends up in the
# message shown to users.
ERROR_BODY_PREVIEW: Final = 200


class RestClientError(Exception):
    """Base exception for REST client errors."""


class AuthenticationError(RestClientError):
    """Raised when authentication fails."""


class ConnectionError(RestClientError):
    """Raised when connection to wallbox fails."""


class HttpRequestError(RestClientError):
    """Raised when the REST API returns an HTTP error status."""

    def __init__(self, status: int, path: str, body: str) -> None:
        preview = " ".join(body.split())[:ERROR_BODY_PREVIEW]
        super().__init__(f"Request to {path} failed with HTTP {status}: {preview}")
        self.status = status
        self.path = path
        self.body = body


class EndpointNotFoundError(RestClientError):
    """Raised when an endpoint does not exist on this firmware (HTTP 404)."""


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

    # Unite-only settings (served via /api/configuration-fields/)
    led_dimming_level: str | None = None
    randomised_delay: int | None = None


def _expect_list(result: Any, path: str) -> list[Any]:
    """Return ``result`` if it is a JSON list, otherwise raise.

    An unexpected shape must not be read as "empty" (no errors, no fields):
    raising lets ``get_data`` keep the previous values instead.
    """

    if not isinstance(result, list):
        msg = f"Unexpected response from {path}: {type(result).__name__}"
        raise RestClientError(msg)
    return result


def _token_lifetime(token: str) -> timedelta:
    """Return how long a JWT stays valid, from its own ``iat``/``exp`` claims.

    The difference of the two claims is used rather than ``exp`` itself, so a
    wallbox clock that is off (no NTP) doesn't make the token look expired or
    valid forever. Falls back to DEFAULT_TOKEN_LIFETIME.
    """

    try:
        payload_b64 = token.split(".")[1]
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4)))
    except IndexError, ValueError, binascii.Error, UnicodeDecodeError:
        return DEFAULT_TOKEN_LIFETIME
    if not isinstance(payload, dict):
        return DEFAULT_TOKEN_LIFETIME
    issued, expires = payload.get("iat"), payload.get("exp")
    if isinstance(issued, (int, float)) and isinstance(expires, (int, float)) and expires > issued:
        return timedelta(seconds=expires - issued)
    return DEFAULT_TOKEN_LIFETIME


class RestClient:
    """Async REST API client for Webasto Next / Ampure Unite wallboxes.

    Provides access to features not available via Modbus. The two models expose
    different REST surfaces, so the client is model-aware:

    - Next: per-section endpoints — firmware/hardware versions, MAC/network
      info, diagnostic counters, LED brightness, free charging, restart.
    - Unite: a single flat ``configuration-fields`` endpoint — free charging,
      LED dimming level, randomised start delay, restart (no diagnostic data).
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        model: str = MODEL_NEXT,
    ) -> None:
        """Initialize the REST client.

        Args:
            host: Wallbox IP address or hostname (an IPv6 literal is bracketed
                automatically).
            username: Web interface username (usually "admin").
            password: Web interface password.
            session: Shared aiohttp session (from
                ``async_get_clientsession(hass, verify_ssl=False)``). The
                wallbox uses a self-signed certificate, hence ``verify_ssl``
                must be disabled by the caller. The session is owned by Home
                Assistant and must not be closed here.
            timeout: Request timeout in seconds.
            model: Wallbox model (``MODEL_NEXT`` or ``MODEL_UNITE``). The Unite
                serves a different REST surface (flat configuration-fields
                endpoint, different field keys and a single update type).
        """
        self._host = host
        self._username = username
        self._password = password
        url_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
        self._base_url = f"https://{url_host}/api"
        self._model = model

        self._session = session
        self._request_timeout = aiohttp.ClientTimeout(total=timeout)
        self._token: str | None = None
        self._token_expires: datetime | None = None
        # Serialises logins: concurrent callers with an expired token must not
        # each log in (the wallbox web UI is single-user, a second login can
        # invalidate the first token).
        self._login_lock = asyncio.Lock()
        self._last_login_error: AuthenticationError | None = None
        self._last_login_failed_at = 0.0

    @property
    def _is_unite(self) -> bool:
        """Return True if this client targets a Webasto / Ampure Unite."""
        return self._model == MODEL_UNITE

    @property
    def is_connected(self) -> bool:
        """Return True if we have a valid token."""
        if self._token is None or self._token_expires is None:
            return False
        return datetime.now(UTC) < self._token_expires - TOKEN_REFRESH_MARGIN

    async def connect(self) -> None:
        """Authenticate against the wallbox REST API.

        Raises:
            AuthenticationError: If the credentials are rejected.
            ConnectionError: If the wallbox can't be reached.
        """
        await self._async_login_once(lambda: True)

    async def disconnect(self) -> None:
        """Forget the auth token.

        The aiohttp session is owned by Home Assistant (shared), so it is
        intentionally not closed here.
        """
        self._token = None
        self._token_expires = None

    async def get_data(
        self,
        previous: RestData | None = None,
        *,
        include_system: bool = True,
    ) -> RestData:
        """Fetch the REST data, keeping ``previous`` values for what wasn't fetched.

        Each endpoint is fetched separately. An endpoint this firmware doesn't
        have (404) or can't be parsed keeps its previous values; a rejected
        login or an unreachable wallbox raises, so the caller keeps its last
        good data instead of replacing it with empty fields.

        Args:
            previous: Last successfully fetched data.
            include_system: Next only: also fetch the slow ``system`` section
                (firmware, MACs, counters, LED brightness).

        Raises:
            AuthenticationError: If the credentials are rejected.
            ConnectionError: If the wallbox can't be reached.
            RestClientError: If no endpoint returned usable data.
        """
        values: dict[str, Any] = asdict(previous) if previous is not None else {}
        if self._is_unite:
            fetchers: list[tuple[str, Callable[[], Awaitable[None]]]] = [
                ("configuration fields", lambda: self._fetch_unite(values)),
            ]
        else:
            fetchers = [
                ("auth section", lambda: self._fetch_section("auth", values)),
                ("current errors", lambda: self._fetch_current_errors(values)),
            ]
            if include_system or previous is None:
                fetchers.insert(
                    0, ("system section", lambda: self._fetch_section("system", values))
                )

        last_error: RestClientError | None = None
        fetched_any = False
        for name, fetch in fetchers:
            try:
                await fetch()
            except AuthenticationError, ConnectionError:
                raise
            except RestClientError as err:
                _LOGGER.debug("Failed to fetch %s: %s", name, err)
                last_error = err
            else:
                fetched_any = True

        if not fetched_any:
            assert last_error is not None
            raise last_error
        return RestData(**values)

    async def _fetch_section(self, section: str, values: dict[str, Any]) -> None:
        fields = await self._get_section(section)
        if section == "system":
            self._parse_system_fields(fields, values)
        else:
            self._parse_auth_fields(fields, values)

    async def _fetch_current_errors(self, values: dict[str, Any]) -> None:
        values["active_errors"] = await self._get_current_errors()

    async def _fetch_unite(self, values: dict[str, Any]) -> None:
        self._parse_unite_fields(await self._get_configuration_fields(), values)

    async def set_led_brightness(self, brightness: int) -> None:
        """Set LED brightness.

        Args:
            brightness: Brightness value 0-100.

        Raises:
            ValueError: If brightness is out of range.
            RestClientError: If the request fails.
        """
        if self._is_unite:
            # The Unite has no 0-100 brightness field; it uses an enum dimming
            # level instead (see set_led_dimming_level).
            msg = "LED brightness is not available on the Unite; use LED dimming level"
            raise RestClientError(msg)

        if not 0 <= brightness <= 100:
            msg = f"Brightness must be 0-100, got {brightness}"
            raise ValueError(msg)

        await self._update_config(
            [
                {
                    "fieldKey": "led-brightness",
                    "value": brightness,
                    "configurationFieldUpdateType": "number-configuration-field-update",
                }
            ]
        )

    async def set_led_dimming_level(self, level: str) -> None:
        """Set the LED dimming level (Unite only).

        Args:
            level: One of ``UNITE_LED_DIMMING_LEVELS``.

        Raises:
            ValueError: If the level is unknown.
            RestClientError: If called on a non-Unite model or the request fails.
        """
        if not self._is_unite:
            msg = "LED dimming level is only available on the Unite"
            raise RestClientError(msg)
        if level not in UNITE_LED_DIMMING_LEVELS:
            msg = f"Unknown LED dimming level {level!r}"
            raise ValueError(msg)

        await self._update_config([self._unite_update("generalSettings.ledDimmingLevel", level)])

    async def set_randomised_delay(self, seconds: int) -> None:
        """Set the randomised charging-start delay in seconds (Unite only).

        Args:
            seconds: 0 (disabled) to ``UNITE_RANDOMISED_DELAY_MAX``.

        Raises:
            ValueError: If the value is out of range.
            RestClientError: If called on a non-Unite model or the request fails.
        """
        if not self._is_unite:
            msg = "Randomised delay is only available on the Unite"
            raise RestClientError(msg)
        if not 0 <= seconds <= UNITE_RANDOMISED_DELAY_MAX:
            msg = f"Randomised delay must be 0-{UNITE_RANDOMISED_DELAY_MAX}, got {seconds}"
            raise ValueError(msg)

        await self._update_config(
            [self._unite_update("generalSettings.randomisedDelayMaximumDuration", str(seconds))]
        )

    async def set_free_charging(self, enabled: bool) -> None:
        """Enable or disable free charging mode.

        Args:
            enabled: True to enable, False to disable.

        Raises:
            RestClientError: If the request fails.
        """
        if self._is_unite:
            await self._update_config(
                [
                    self._unite_update(
                        "ocppConfigurations.freeModeActive", "TRUE" if enabled else "FALSE"
                    )
                ]
            )
            return
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
        if self._is_unite:
            await self._update_config(
                [self._unite_update("ocppConfigurations.freeModeRfid", tag_id)]
            )
            return
        await self._update_config(
            [
                {
                    "fieldKey": "free-charging-alais",
                    "value": tag_id,
                    "configurationFieldUpdateType": "simple-string-configuration-field-update",
                }
            ]
        )

    @staticmethod
    def _unite_update(field_key: str, value: str) -> dict[str, Any]:
        """Build a Unite configuration-update payload entry.

        The Unite accepts (and only needs) ``fieldKey`` + ``value`` — unlike the
        Next it does not require a ``configurationFieldUpdateType``. This is the
        exact shape verified against FW 3.187 hardware in issue #97; we send
        nothing beyond it so a write can't be rejected over an extra property.
        """
        return {
            "fieldKey": field_key,
            "value": value,
        }

    async def restart_system(self) -> None:
        """Trigger a system restart.

        Sent once, never retried. The wallbox often drops the connection while
        it goes down, so a disconnect or timeout after the request was sent is
        treated as success.

        Raises:
            RestClientError: If the request is rejected.
        """
        try:
            await self._request("POST", "/custom-actions/restart-system", attempts=1)
        except ConnectionError as err:
            if isinstance(err.__cause__, (aiohttp.ServerDisconnectedError, TimeoutError)):
                _LOGGER.debug("Wallbox dropped the connection while restarting: %s", err)
                return
            raise

    # -------------------------------------------------------------------------
    # Private methods
    # -------------------------------------------------------------------------

    async def _ensure_token(self) -> str:
        """Return a valid token, logging in first if needed."""
        token = self._token
        if token is not None and self.is_connected:
            return token
        return await self._async_login_once(lambda: self._token is None or not self.is_connected)

    async def _relogin_after_401(self, rejected_token: str) -> str:
        """Log in again unless another caller already replaced the rejected token.

        A failed re-login by another caller is shared (see _async_login_once).
        """
        return await self._async_login_once(lambda: self._token in (rejected_token, None))

    async def _async_login_once(self, needs_login: Callable[[], bool]) -> str:
        """Log in under the lock, sharing a recent rejection instead of repeating it.

        Requests that queued behind a login get its token. If the login was
        just rejected, every caller in the next LOGIN_FAILURE_COOLDOWN seconds
        gets that same error, so a burst of requests with a wrong password
        doesn't become a burst of rejected logins (the web interface can lock
        the account after repeated failures).
        """
        loop = asyncio.get_running_loop()
        async with self._login_lock:
            if (
                self._token is None
                and self._last_login_error is not None
                and loop.time() - self._last_login_failed_at < LOGIN_FAILURE_COOLDOWN
            ):
                raise self._last_login_error
            if needs_login():
                self._token = None
                try:
                    await self._login()
                except AuthenticationError as err:
                    # Only rejected credentials are shared; an unreachable web
                    # interface may be back for the very next caller.
                    self._last_login_error = err
                    self._last_login_failed_at = loop.time()
                    raise
                self._last_login_error = None
            if self._token is None:  # pragma: no cover - _login sets it or raises
                msg = "Not logged in"
                raise RestClientError(msg)
            return self._token

    async def _login(self) -> None:
        """Authenticate and obtain a JWT token. Caller holds the login lock."""
        url = f"{self._base_url}/login"
        payload = {"username": self._username, "password": self._password}

        try:
            async with self._session.post(url, json=payload, timeout=self._request_timeout) as resp:
                if resp.status in (401, 403):
                    msg = "The wallbox rejected the username or password"
                    raise AuthenticationError(msg)
                if resp.status != 200:
                    # Not a credentials problem (e.g. the wallbox web server is
                    # still coming up) — treat it as a connection error so the
                    # caller retries instead of flagging the credentials.
                    msg = f"Login failed with HTTP {resp.status}"
                    raise ConnectionError(msg)
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            msg = f"Connection to {self._host} failed: {err!r}"
            raise ConnectionError(msg) from err
        except ValueError as err:
            msg = "Login returned an invalid response"
            raise RestClientError(msg) from err

        token = data.get("access_token") if isinstance(data, dict) else None
        if not isinstance(token, str) or not token:
            # A 200 without a token is a malformed answer (e.g. the web server
            # is still starting), not a rejected password: retry later.
            msg = "No access_token in login response"
            raise RestClientError(msg)
        self._token = token
        self._token_expires = datetime.now(UTC) + _token_lifetime(token)
        _LOGGER.debug("Authenticated to REST API (token valid until %s)", self._token_expires)

    async def _get(self, path: str) -> Any:
        """Make authenticated GET request."""
        return await self._request("GET", path, attempts=GET_ATTEMPTS)

    async def _post(
        self,
        path: str,
        json: Mapping[str, Any] | list[dict[str, Any]] | None = None,
    ) -> Any:
        """Make authenticated POST request (sent once)."""
        return await self._request("POST", path, json=json, attempts=1)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | list[dict[str, Any]] | None = None,
        attempts: int,
    ) -> Any:
        """Make an authenticated request.

        A 401 triggers one re-login and one more try (not counted as an
        attempt). A second 401 right after a fresh login means the
        credentials no longer work and raises ``AuthenticationError``.
        Transport errors are retried up to ``attempts`` times in total.
        """
        token = await self._ensure_token()
        url = f"{self._base_url}{path}"
        relogged_in = False
        attempt = 0

        while True:
            attempt += 1
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            try:
                async with self._session.request(
                    method, url, headers=headers, json=json, timeout=self._request_timeout
                ) as resp:
                    if resp.status == 401:
                        if relogged_in:
                            msg = f"Request to {path} was rejected after a fresh login"
                            raise AuthenticationError(msg)
                        _LOGGER.debug("Token rejected (401), re-authenticating")
                        token = await self._relogin_after_401(token)
                        relogged_in = True
                        attempt -= 1
                        continue
                    if resp.status == 404:
                        msg = f"Endpoint not found: {path}"
                        raise EndpointNotFoundError(msg)
                    if resp.status >= 400:
                        raise HttpRequestError(resp.status, path, await resp.text())
                    if resp.content_type == "application/json":
                        return await resp.json()
                    return await resp.text()
            except (aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.debug(
                    "Attempt %s/%s to %s %s failed: %r", attempt, attempts, method, path, err
                )
                if attempt >= attempts:
                    msg = f"{method} {path} failed: {err!r}"
                    raise ConnectionError(msg) from err
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
            except ValueError as err:
                msg = f"{method} {path} returned an invalid response"
                raise RestClientError(msg) from err

    async def _get_section(self, section: str) -> list[dict[str, Any]]:
        """Get configuration fields for a section."""
        return _expect_list(await self._get(f"/sections/{section}"), f"/sections/{section}")

    async def _get_current_errors(self) -> list[str]:
        """Get list of current active errors."""
        result = _expect_list(await self._get("/current-errors"), "/current-errors")
        # Extract error descriptions or codes
        errors = []
        for error in result:
            if isinstance(error, dict):
                desc = error.get("errorDescription") or error.get("errorCode", "Unknown")
                errors.append(str(desc))
            else:
                errors.append(str(error))
        return errors

    async def _get_configuration_fields(self) -> list[dict[str, Any]]:
        """Get the Unite's flat list of configuration fields."""
        return _expect_list(await self._get("/configuration-fields/"), "/configuration-fields/")

    async def _update_config(self, updates: list[dict[str, Any]]) -> None:
        """Update configuration fields."""
        await self._post("/configuration-updates", json=updates)

    def _parse_unite_fields(self, fields: list[dict[str, Any]], values: dict[str, Any]) -> None:
        """Parse the Unite's flat configuration fields into values dict."""
        for field in fields:
            key = field.get("fieldKey", "")
            value = field.get("value")

            if key == "ocppConfigurations.freeModeActive":
                values["free_charging_enabled"] = self._parse_bool(value)
            elif key == "ocppConfigurations.freeModeRfid":
                values["free_charging_tag_id"] = value
            elif key == "generalSettings.ledDimmingLevel":
                values["led_dimming_level"] = value if value in UNITE_LED_DIMMING_LEVELS else None
            elif key == "generalSettings.randomisedDelayMaximumDuration":
                values["randomised_delay"] = self._safe_int(value)

    @staticmethod
    def _parse_bool(value: Any) -> bool | None:
        """Parse the Unite's boolean fields (returned as "TRUE"/"FALSE" strings).

        Returns None for unrecognised values rather than silently treating them
        as False, so an unexpected API value surfaces as "unknown" instead of a
        wrong state.
        """
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("true", "1", "on", "yes"):
            return True
        if text in ("false", "0", "off", "no"):
            return False
        return None

    def _parse_system_fields(self, fields: list[dict[str, Any]], values: dict[str, Any]) -> None:
        """Parse system section fields into values dict."""
        for field in fields:
            key = field.get("fieldKey", "")
            value = field.get("value")

            if key == "comboard-sw-version":
                values["comboard_sw_version"] = self._safe_str(value)
            elif key == "powerboard-sw-version":
                values["powerboard_sw_version"] = self._safe_str(value)
            elif key == "comboard-hw-version":
                values["comboard_hw_version"] = self._safe_str(value)
            elif key == "powerboard-hw-version":
                values["powerboard_hw_version"] = self._safe_str(value)
            elif key == "MAC-Address Eth0":
                values["mac_address_ethernet"] = self._safe_str(value)
            elif key == "MAC-Address WiFi":
                values["mac_address_wifi"] = self._safe_str(value)
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
                values["free_charging_enabled"] = self._parse_bool(value)
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
        except ValueError, TypeError:
            return None

    @staticmethod
    def _safe_str(value: Any) -> str | None:
        """Safely convert value to a stripped string, mapping empty to None.

        These values end up in ``DeviceInfo`` (sw/hw version, MAC connections),
        and the device registry rejects non-string fields from HA 2026.12 on.
        """
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _extract_ip(interfaces_str: str | None) -> str | None:
        """Extract primary IP address from interfaces string."""
        if not interfaces_str:
            return None

        # Look for IPv4 addresses (exclude 127.x.x.x and 172.20.x.x which is AP)
        import re

        pattern = r"inet\s+(\d+\.\d+\.\d+\.\d+)"
        matches: list[str] = re.findall(pattern, interfaces_str)

        for ip in matches:
            if not ip.startswith("127.") and not ip.startswith("172.20."):
                return ip
        return matches[0] if matches else None
