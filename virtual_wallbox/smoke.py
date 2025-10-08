"""Home Assistant smoke test for the Webasto Next Modbus integration.

This script exercises the core service surface of the integration against a
running Home Assistant instance that is connected to the virtual wallbox
simulator. It verifies that the Modbus bridge responds to service calls and
that key telemetry entities update accordingly.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from custom_components.webasto_next_modbus.const import (
    DOMAIN,
    SERVICE_SEND_KEEPALIVE,
    SERVICE_SET_CURRENT,
    SERVICE_SET_FAILSAFE,
    SERVICE_START_SESSION,
    SERVICE_STOP_SESSION,
    build_device_slug,
)

DEFAULT_TIMEOUT = 30.0
DEFAULT_POLL_INTERVAL = 1.0


class HomeAssistantAPI:
    """Minimal REST client for interacting with Home Assistant."""

    def __init__(self, base_url: str, token: str, timeout: float) -> None:
        if not token:
            raise ValueError("Home Assistant long-lived access token is required")
        sanitised_token = token.strip()
        try:
            sanitised_token.encode("ascii")
        except UnicodeEncodeError as err:
            raise ValueError(
                "Home Assistant token contains non-ASCII characters. Copy the complete token "
                "from Settings → Security → Long-Lived Access Tokens without ellipses or "
                "smart quotes."
            ) from err
        self._base_url = base_url.rstrip("/")
        self._token = sanitised_token
        self._timeout = timeout

    def get(self, path: str) -> Any:
        """Issue a GET request and return parsed JSON."""

        return self._request("GET", path)

    def post(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        """Issue a POST request with JSON payload."""

        return self._request("POST", path, payload)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = f"{self._base_url}{path}"
        data: bytes | None = None
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

        if payload is not None:
            data = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(url, data=data, method=method, headers=headers)

        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                if response.status >= 400:
                    raise RuntimeError(f"HTTP {response.status}: {response.reason}")
                raw = response.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"HTTP error {err.code} for {method} {path}: {detail or err.reason}"
            ) from err
        except urllib.error.URLError as err:  # pragma: no cover - network failures
            raise RuntimeError(f"Failed to reach Home Assistant: {err}") from err


@dataclass(slots=True)
class EntityRefs:
    """Resolved entity identifiers tied to a specific wallbox."""

    config_entry_id: str | None
    charging_state: str
    charge_power: str
    failsafe_current: str
    failsafe_timeout: str
    keepalive_button: str


class IntegrationSmokeTest:
    """Drive the smoke test workflow against Home Assistant."""

    def __init__(
        self,
        api: HomeAssistantAPI,
        host: str,
        unit_id: int,
        timeout: float,
        poll_interval: float,
        entity_prefix: str,
    ) -> None:
        self._api = api
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._slug = build_device_slug(host, unit_id)
        self._entity_prefix = entity_prefix
        self._entities = self._resolve_entities()

    def run(
        self,
        *,
        set_current_amps: int,
        failsafe_amps: int,
        failsafe_timeout: int,
    ) -> None:
        self._print("Validating Home Assistant connectivity...")
        self._api.get("/api/")

        self._print("Ensuring wallbox entities are available...")
        self._wait_for_state(
            self._entities.charging_state,
            predicate=lambda state: state in {"idle", "unknown"},
            description="charging state availability",
        )
        self._wait_for_numeric(
            self._entities.charge_power,
            predicate=lambda value: value is None or abs(value) < 0.5,
            description="initial charge power",
        )

        config_entry_id = self._entities.config_entry_id
        service_kwargs = {"config_entry_id": config_entry_id} if config_entry_id else {}

        self._print(f"Setting dynamic charging current to {set_current_amps} A...")
        self._call_service(SERVICE_SET_CURRENT, {**service_kwargs, "amps": set_current_amps})

        self._print(
            f"Configuring fail-safe current to {failsafe_amps} A (timeout {failsafe_timeout} s)..."
        )
        self._call_service(
            SERVICE_SET_FAILSAFE,
            {
                **service_kwargs,
                "amps": failsafe_amps,
                "timeout_s": failsafe_timeout,
            },
        )
        self._wait_for_state(
            self._entities.failsafe_current,
            predicate=lambda state: state == str(failsafe_amps),
            description="fail-safe current",
        )
        self._wait_for_state(
            self._entities.failsafe_timeout,
            predicate=lambda state: state == str(failsafe_timeout),
            description="fail-safe timeout",
        )

        self._print("Triggering keep-alive button...")
        self._call_service(SERVICE_SEND_KEEPALIVE, service_kwargs)

        self._print("Starting charging session...")
        self._call_service(SERVICE_START_SESSION, service_kwargs)
        self._wait_for_state(
            self._entities.charging_state,
            predicate=lambda state: state == "charging",
            description="charging state",
        )
        self._wait_for_numeric(
            self._entities.charge_power,
            predicate=lambda value: value is not None and value > 0.0,
            description="charge power",
        )

        self._print("Stopping charging session...")
        self._call_service(SERVICE_STOP_SESSION, service_kwargs)
        self._wait_for_state(
            self._entities.charging_state,
            predicate=lambda state: state == "idle",
            description="charging state",
        )
        self._wait_for_numeric(
            self._entities.charge_power,
            predicate=lambda value: value is not None and abs(value) < 0.5,
            description="charge power",
        )

        self._print("Smoke test completed successfully ✅")

    def _resolve_entities(self) -> EntityRefs:
        try:
            registry_response = self._api.post(
                "/api/config/entity_registry/list",
                {},
            )
        except RuntimeError as err:
            if "404" not in str(err):
                raise
            try:
                registry_response = self._api.get("/api/config/entity_registry")
            except RuntimeError as fallback_err:
                if "404" not in str(fallback_err):
                    raise
                return self._resolve_entities_from_states()
        entries = _extract_entity_entries(registry_response)

        prefix = f"{self._slug}-"
        matches = [entry for entry in entries if str(entry.get("unique_id", "")).startswith(prefix)]
        if not matches:
            return self._resolve_entities_from_states()

        config_entry_ids = {
            entry.get("config_entry_id")
            for entry in matches
            if entry.get("config_entry_id") is not None
        }
        config_entry_id = next(iter(config_entry_ids), None)

        def resolve(unique_suffix: str) -> str:
            unique_id = f"{prefix}{unique_suffix}"
            for entry in matches:
                if entry.get("unique_id") == unique_id:
                    entity_id = entry.get("entity_id")
                    if not entity_id:
                        break
                    return str(entity_id)
            raise RuntimeError(f"Entity with unique id {unique_id} not found in registry")

        return EntityRefs(
            config_entry_id=config_entry_id,
            charging_state=resolve("charging_state"),
            charge_power=resolve("charge_power_w"),
            failsafe_current=resolve("failsafe_current_a"),
            failsafe_timeout=resolve("failsafe_timeout_s"),
            keepalive_button=resolve("send_keepalive"),
        )

    def _resolve_entities_from_states(self) -> EntityRefs:
        base = self._entity_prefix
        candidates = {
            "charging_state": f"sensor.{base}_charging_state",
            "charge_power": f"sensor.{base}_charge_power",
            "failsafe_current": f"number.{base}_failsafe_current",
            "failsafe_timeout": f"number.{base}_failsafe_timeout",
            "keepalive_button": f"button.{base}_send_keepalive",
        }

        for _friendly, entity_id in candidates.items():
            try:
                self._read_state(entity_id)
            except RuntimeError as err:
                raise RuntimeError(
                    f"Entity '{entity_id}' not found via /api/states. "
                    "If you renamed entities, pass the custom ID with "
                    "--entity-prefix or Home Assistant's naming convention."
                ) from err

        return EntityRefs(
            config_entry_id=None,
            charging_state=candidates["charging_state"],
            charge_power=candidates["charge_power"],
            failsafe_current=candidates["failsafe_current"],
            failsafe_timeout=candidates["failsafe_timeout"],
            keepalive_button=candidates["keepalive_button"],
        )

    def _call_service(self, service: str, data: dict[str, Any]) -> None:
        path = f"/api/services/{DOMAIN}/{service}"
        self._api.post(path, data)

    def _assert_state(self, entity_id: str, *, expected: str, description: str) -> None:
        state = self._read_state(entity_id)
        if state != expected:
            raise RuntimeError(
                f"Unexpected {description} for {entity_id}: got '{state}', expected '{expected}'"
            )

    def _assert_numeric(
        self, entity_id: str, *, expected: float, tolerance: float, description: str
    ) -> None:
        value = self._read_numeric(entity_id)
        if value is None or abs(value - expected) > tolerance:
            raise RuntimeError(
                f"Unexpected {description} for {entity_id}: got {value}, expected ~{expected}"
            )

    def _wait_for_state(
        self,
        entity_id: str,
        *,
        predicate: Callable[[str], bool],
        description: str,
    ) -> str:
        deadline = time.monotonic() + self._timeout
        while True:
            state = self._read_state(entity_id)
            if predicate(state):
                return state
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Timed out waiting for {description} to update (last={state})")
            time.sleep(self._poll_interval)

    def _wait_for_numeric(
        self,
        entity_id: str,
        *,
        predicate: Callable[[float | None], bool],
        description: str,
    ) -> float | None:
        deadline = time.monotonic() + self._timeout
        while True:
            value = self._read_numeric(entity_id)
            if predicate(value):
                return value
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Timed out waiting for {description} to update (last={value})")
            time.sleep(self._poll_interval)

    def _read_state(self, entity_id: str) -> str:
        encoded_id = urllib.parse.quote(entity_id, safe="")
        data = self._api.get(f"/api/states/{encoded_id}")
        if not isinstance(data, dict) or "state" not in data:
            raise RuntimeError(f"Unexpected response while reading state for {entity_id}: {data!r}")
        return str(data["state"]).lower()

    def _read_numeric(self, entity_id: str) -> float | None:
        state = self._read_state(entity_id)
        if state in {"unknown", "unavailable", "none"}:
            return None
        try:
            return float(state)
        except ValueError:
            return None

    def _print(self, message: str) -> None:
        print(f"[webasto-smoke] {message}")


def _extract_entity_entries(response: Any) -> Iterable[dict[str, Any]]:
    """Normalise the entity registry response shape."""

    if isinstance(response, dict):
        data = response
        if "data" in data and isinstance(data["data"], dict):
            data = data["data"]
        entities = data.get("entities")
        if isinstance(entities, list):
            return entities
    if isinstance(response, list):
        return response
    raise RuntimeError(f"Cannot parse entity registry response: {response!r}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ha-url",
        default=os.environ.get("HA_URL", "http://127.0.0.1:8123"),
        help="Base URL of the Home Assistant instance (default: %(default)s)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("HA_TOKEN"),
        help="Long-lived access token with admin permissions (defaults to HA_TOKEN env)",
    )
    parser.add_argument(
        "--device-host",
        required=True,
        help="Host/IP used in the Webasto Next Modbus config entry",
    )
    parser.add_argument(
        "--unit-id",
        type=int,
        default=255,
        help="Unit ID of the wallbox (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Maximum seconds to wait for state transitions (default: %(default)s)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help="Seconds between polling cycles while waiting for updates (default: %(default)s)",
    )
    parser.add_argument(
        "--set-current",
        type=int,
        default=16,
        help="Current (A) used for the set_current service call",
    )
    parser.add_argument(
        "--failsafe-amps",
        type=int,
        default=12,
        help="Fail-safe current (A) to apply during the test",
    )
    parser.add_argument(
        "--failsafe-timeout",
        type=int,
        default=45,
        help="Fail-safe timeout (s) to apply during the test",
    )
    parser.add_argument(
        "--entity-prefix",
        default="webasto_next_wallbox",
        help="Entity ID prefix used for the integration (default: %(default)s)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        api = HomeAssistantAPI(args.ha_url, args.token, timeout=args.timeout)
    except ValueError as err:
        print(f"[webasto-smoke] ❌ {err}", file=sys.stderr)
        return 1

    tester = IntegrationSmokeTest(
        api,
        host=args.device_host,
        unit_id=args.unit_id,
        timeout=args.timeout,
        poll_interval=args.poll_interval,
        entity_prefix=args.entity_prefix,
    )

    try:
        tester.run(
            set_current_amps=args.set_current,
            failsafe_amps=args.failsafe_amps,
            failsafe_timeout=args.failsafe_timeout,
        )
    except Exception as err:  # pragma: no cover - smoke tests are best-effort
        print(f"[webasto-smoke] ❌ {err}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
