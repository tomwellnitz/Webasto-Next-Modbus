"""Tests for the entity lookup of the ``webasto-smoke`` script."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.webasto_next_modbus.const import DOMAIN
from virtual_wallbox.smoke import IntegrationSmokeTest

KEYS = {
    "charging_state": "sensor.wallbox_charging_state",
    "active_power_total_w": "sensor.wallbox_active_power_total",
    "failsafe_current_a": "number.wallbox_failsafe_current",
    "failsafe_timeout_s": "number.wallbox_failsafe_timeout",
    "send_keepalive": "button.wallbox_send_keepalive",
}


def _registry(*entry_ids: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = [
        {
            "platform": "other_integration",
            "config_entry_id": "unrelated",
            "unique_id": "unrelated-charging_state",
            "entity_id": "sensor.other",
        }
    ]
    for entry_id in entry_ids:
        for key, entity_id in KEYS.items():
            suffix = "" if entry_id == entry_ids[0] else f"_{entry_id}"
            entries.append(
                {
                    "platform": DOMAIN,
                    "config_entry_id": entry_id,
                    "unique_id": f"{entry_id}-{key}",
                    "entity_id": f"{entity_id}{suffix}",
                }
            )
    return entries


class _FakeAPI:
    def __init__(self, registry: list[dict[str, Any]]) -> None:
        self._registry = registry

    def post(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        assert path == "/api/config/entity_registry/list"
        return self._registry

    def get(self, path: str) -> Any:
        raise RuntimeError(f"unexpected GET {path}")


def _tester(registry: list[dict[str, Any]], config_entry_id: str | None) -> IntegrationSmokeTest:
    return IntegrationSmokeTest(
        _FakeAPI(registry),  # type: ignore[arg-type]
        config_entry_id=config_entry_id,
        timeout=1.0,
        poll_interval=0.1,
        entity_prefix="wallbox",
    )


def test_resolves_the_only_config_entry() -> None:
    tester = _tester(_registry("entry-a"), None)

    refs = tester._entities
    assert refs.config_entry_id == "entry-a"
    assert refs.charging_state == "sensor.wallbox_charging_state"
    assert refs.charge_power == "sensor.wallbox_active_power_total"
    assert refs.failsafe_current == "number.wallbox_failsafe_current"
    assert refs.keepalive_button == "button.wallbox_send_keepalive"


def test_explicit_config_entry_is_used() -> None:
    tester = _tester(_registry("entry-a", "entry-b"), "entry-b")

    assert tester._entities.config_entry_id == "entry-b"
    assert tester._entities.charging_state == "sensor.wallbox_charging_state_entry-b"


def test_several_config_entries_need_an_explicit_choice() -> None:
    with pytest.raises(RuntimeError, match="--config-entry-id"):
        _tester(_registry("entry-a", "entry-b"), None)
