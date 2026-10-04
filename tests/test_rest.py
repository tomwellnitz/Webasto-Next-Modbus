"""REST client and REST coordinator tests (real Home Assistant, mocked HTTP)."""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from custom_components.webasto_next_modbus.const import (
    CONF_MODEL,
    CONF_REST_ENABLED,
    CONF_REST_PASSWORD,
    CONF_REST_USERNAME,
    CONF_SCAN_INTERVAL,
    CONF_VARIANT,
    DOMAIN,
    MODEL_NEXT,
    MODEL_UNITE,
    VARIANT_22_KW,
)
from custom_components.webasto_next_modbus.rest_client import (
    AuthenticationError,
    ConnectionError,
    HttpRequestError,
    RestClient,
    RestData,
    _token_lifetime,
)
from tests.conftest import HA_HOST, make_config_entry
from virtual_wallbox.simulator import VirtualWallboxState

pytestmark = pytest.mark.usefixtures("enable_custom_integrations", "fake_pymodbus")

BASE = f"https://{HA_HOST}/api"
JSON = {"Content-Type": "application/json"}
REST_OPTIONS = {
    CONF_SCAN_INTERVAL: 10,
    CONF_VARIANT: VARIANT_22_KW,
    CONF_MODEL: MODEL_NEXT,
    CONF_REST_ENABLED: True,
    CONF_REST_USERNAME: "admin",
    CONF_REST_PASSWORD: "secret",
}


def _jwt(iat: int, exp: int) -> str:
    def _b64(data: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    return f"{_b64({'alg': 'HS256'})}.{_b64({'iat': iat, 'exp': exp})}.signature"


def _mock_next_api(aioclient_mock: AiohttpClientMocker, *, system_status: int = 200) -> None:
    aioclient_mock.post(f"{BASE}/login", json={"access_token": "token-1"}, headers=JSON)
    aioclient_mock.get(
        f"{BASE}/sections/system",
        status=system_status,
        json=[
            {"fieldKey": "comboard-sw-version", "value": "3.1.27"},
            {"fieldKey": "comboard-hw-version", "value": "2"},
            {"fieldKey": "MAC-Address Eth0", "value": "AA:BB:CC:DD:EE:FF"},
            {"fieldKey": "led-brightness", "value": 40},
        ],
        headers=JSON,
    )
    aioclient_mock.get(
        f"{BASE}/sections/auth",
        json=[{"fieldKey": "free-charging", "value": "false"}],
        headers=JSON,
    )
    aioclient_mock.get(f"{BASE}/current-errors", json=[], headers=JSON)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    # The initial REST fetch runs as a background task.
    rest = entry.runtime_data.rest_coordinator
    if rest is not None and rest.initial_refresh is not None:
        await rest.initial_refresh
        await hass.async_block_till_done()


@pytest.fixture
async def rest_entry(
    hass: HomeAssistant, wallbox: VirtualWallboxState
) -> AsyncGenerator[MockConfigEntry]:
    entry = make_config_entry(options=REST_OPTIONS)
    yield entry
    if entry.state is ConfigEntryState.LOADED:
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


async def test_rest_entities_and_device_info(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, rest_entry: MockConfigEntry
) -> None:
    """REST data shows up in entities and on the device page."""

    _mock_next_api(aioclient_mock)
    await _setup(hass, rest_entry)

    assert hass.states.get("switch.wallbox_free_charging").state == "off"
    assert hass.states.get("number.wallbox_led_brightness").state == "40.0"
    assert hass.states.get("sensor.wallbox_active_errors").state == "ok"

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), rest_entry.entry_id)
    assert len(devices) == 1
    device = devices[0]
    assert device is not None
    assert device.sw_version == "3.1.27"
    assert device.hw_version == "2"
    assert (dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff") in device.connections
    assert device.configuration_url == f"https://{HA_HOST}"


async def test_rest_down_at_startup_recovers_without_reload(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, rest_entry: MockConfigEntry
) -> None:
    """REST entities exist while the web interface is down and come back on their own."""

    aioclient_mock.post(f"{BASE}/login", exc=aiohttp.ClientConnectionError("refused"))
    await _setup(hass, rest_entry)

    assert rest_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.wallbox_charge_point_state").state == "available"
    assert hass.states.get("switch.wallbox_free_charging").state == STATE_UNAVAILABLE

    aioclient_mock.clear_requests()
    _mock_next_api(aioclient_mock)
    await rest_entry.runtime_data.rest_coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("switch.wallbox_free_charging").state == "off"


@pytest.mark.parametrize("status", [401, 403])
async def test_rejected_credentials_start_reauth_and_stop_polling(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    rest_entry: MockConfigEntry,
    status: int,
) -> None:
    """Wrong REST credentials start reauth once; Modbus keeps working."""

    aioclient_mock.post(f"{BASE}/login", status=status)
    await _setup(hass, rest_entry)

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]
    assert hass.states.get("sensor.wallbox_charge_point_state").state == "available"
    rest = rest_entry.runtime_data.rest_coordinator
    assert rest.last_update_success is False
    # No further refresh is scheduled after an authentication failure.
    assert rest._unsub_refresh is None
    assert aioclient_mock.call_count == 1


async def test_failed_fetch_keeps_last_good_data(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, rest_entry: MockConfigEntry
) -> None:
    """A failing poll doesn't replace the data with empty values."""

    _mock_next_api(aioclient_mock)
    await _setup(hass, rest_entry)
    rest = rest_entry.runtime_data.rest_coordinator
    good = rest.data

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/sections/system", exc=aiohttp.ClientConnectionError())
    aioclient_mock.get(f"{BASE}/sections/auth", exc=aiohttp.ClientConnectionError())
    aioclient_mock.get(f"{BASE}/current-errors", exc=aiohttp.ClientConnectionError())
    await rest.async_refresh()

    assert rest.last_update_success is False
    assert rest.data is good
    assert hass.states.get("switch.wallbox_free_charging").state == STATE_UNAVAILABLE


async def test_slow_section_does_not_fail_the_poll(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, rest_entry: MockConfigEntry
) -> None:
    """A timed-out section keeps its values; the other endpoints still update."""

    _mock_next_api(aioclient_mock)
    await _setup(hass, rest_entry)
    rest = rest_entry.runtime_data.rest_coordinator

    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{BASE}/login", json={"access_token": "token-1"}, headers=JSON)
    aioclient_mock.get(f"{BASE}/sections/system", exc=TimeoutError())
    aioclient_mock.get(
        f"{BASE}/sections/auth",
        json=[{"fieldKey": "free-charging", "value": "true"}],
        headers=JSON,
    )
    aioclient_mock.get(
        f"{BASE}/current-errors", json=[{"errorDescription": "Overheating"}], headers=JSON
    )
    await rest.async_refresh_after_write()  # includes the system section
    await hass.async_block_till_done()

    assert rest.last_update_success is True
    assert hass.states.get("switch.wallbox_free_charging").state == "on"
    assert hass.states.get("sensor.wallbox_active_errors").state == "Overheating"
    # The system section kept its previous values ...
    assert hass.states.get("number.wallbox_led_brightness").state == "40.0"
    # ... and a timeout is not retried.
    system_calls = [call for call in aioclient_mock.mock_calls if "sections/system" in str(call[1])]
    assert len(system_calls) == 1

    # The failed section is tried again on the next regular poll, not only
    # after REST_SYSTEM_SECTION_INTERVAL.
    await rest.async_refresh()
    system_calls = [call for call in aioclient_mock.mock_calls if "sections/system" in str(call[1])]
    assert len(system_calls) == 2


async def test_missing_endpoint_keeps_previous_values(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, rest_entry: MockConfigEntry
) -> None:
    """A 404 on one section keeps that section's previous values."""

    _mock_next_api(aioclient_mock)
    await _setup(hass, rest_entry)
    rest = rest_entry.runtime_data.rest_coordinator

    aioclient_mock.clear_requests()
    _mock_next_api(aioclient_mock, system_status=404)
    await rest.async_refresh_after_write()

    assert rest.last_update_success is True
    assert rest.data.comboard_sw_version == "3.1.27"


async def test_unite_gets_no_next_only_sensors(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, wallbox: VirtualWallboxState
) -> None:
    entry = make_config_entry(options={**REST_OPTIONS, CONF_MODEL: MODEL_UNITE}, model=MODEL_UNITE)
    aioclient_mock.post(f"{BASE}/login", json={"access_token": "t"}, headers=JSON)
    aioclient_mock.get(
        f"{BASE}/configuration-fields/",
        json=[{"fieldKey": "ocppConfigurations.freeModeActive", "value": "TRUE"}],
        headers=JSON,
    )
    await _setup(hass, entry)

    assert hass.states.get("switch.wallbox_free_charging").state == "on"
    assert hass.states.get("sensor.wallbox_active_errors") is None
    assert hass.states.get("sensor.wallbox_plug_cycles") is None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_restart_is_sent_once_and_disconnect_counts_as_success(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, rest_entry: MockConfigEntry
) -> None:
    _mock_next_api(aioclient_mock)
    aioclient_mock.post(
        f"{BASE}/custom-actions/restart-system",
        exc=aiohttp.ServerDisconnectedError(),
    )
    await _setup(hass, rest_entry)
    calls_before = aioclient_mock.call_count

    await hass.services.async_call(DOMAIN, "restart_wallbox", {}, blocking=True)

    assert aioclient_mock.call_count == calls_before + 1


async def test_options_flow_reports_rejected_password(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, rest_entry: MockConfigEntry
) -> None:
    _mock_next_api(aioclient_mock)
    await _setup(hass, rest_entry)

    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{BASE}/login", status=401)
    result = await hass.config_entries.options.async_init(rest_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**REST_OPTIONS, CONF_REST_PASSWORD: "wrong"}
    )

    assert result["errors"] == {"base": "invalid_auth"}


# --------------------------------------------------------------------------- #
# RestClient unit tests
# --------------------------------------------------------------------------- #


@pytest.fixture
async def client(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> RestClient:
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    return RestClient(HA_HOST, "admin", "secret", async_get_clientsession(hass))


async def test_concurrent_requests_log_in_once(
    client: RestClient, aioclient_mock: AiohttpClientMocker
) -> None:
    async def _slow_login(method: str, url: Any, data: Any) -> Any:
        await asyncio.sleep(0.01)
        return AiohttpClientMockResponse(method, url, json={"access_token": "t"}, headers=JSON)

    _mock_next_api(aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{BASE}/login", side_effect=_slow_login)
    aioclient_mock.get(f"{BASE}/sections/auth", json=[], headers=JSON)

    await asyncio.gather(*(client._get("/sections/auth") for _ in range(5)))

    logins = [call for call in aioclient_mock.mock_calls if str(call[1]).endswith("/login")]
    assert len(logins) == 1


async def test_persistent_401_after_relogin_is_an_auth_error(
    client: RestClient, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE}/login", json={"access_token": "t"}, headers=JSON)
    aioclient_mock.get(f"{BASE}/sections/auth", status=401)

    with pytest.raises(AuthenticationError):
        await client._get("/sections/auth")


async def test_login_timeout_is_a_connection_error(
    client: RestClient, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE}/login", exc=TimeoutError())

    with pytest.raises(ConnectionError):
        await client.connect()


async def test_get_is_retried_once_post_never(
    client: RestClient, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE}/login", json={"access_token": "t"}, headers=JSON)
    aioclient_mock.get(f"{BASE}/sections/auth", exc=aiohttp.ClientConnectionError())
    aioclient_mock.post(f"{BASE}/configuration-updates", exc=aiohttp.ClientConnectionError())

    with patch("custom_components.webasto_next_modbus.rest_client.asyncio.sleep", AsyncMock()):
        with pytest.raises(ConnectionError):
            await client._get("/sections/auth")
        with pytest.raises(ConnectionError):
            await client.set_free_charging(True)

    gets = [c for c in aioclient_mock.mock_calls if c[0] == "GET"]
    updates = [c for c in aioclient_mock.mock_calls if str(c[1]).endswith("configuration-updates")]
    assert len(gets) == 2
    assert len(updates) == 1


def test_token_lifetime_uses_relative_claims() -> None:
    """Lifetime comes from exp - iat, independent of the wallbox clock."""

    assert _token_lifetime(_jwt(1_000, 1_000 + 7_200)).total_seconds() == 7_200
    assert _token_lifetime("not-a-jwt").total_seconds() == 3_600


def test_ipv6_host_is_bracketed() -> None:
    rest = RestClient("fd00::1", "admin", "secret", AsyncMock())
    assert rest._base_url == "https://[fd00::1]/api"


def test_http_error_message_is_truncated() -> None:
    err = HttpRequestError(500, "/x", "<html>" + "a" * 5_000 + "</html>")
    assert len(str(err)) < 300
    assert err.body.endswith("</html>")


@pytest.mark.parametrize(("raw", "expected"), [("false", False), ("ON", True), ("?", None)])
def test_next_free_charging_is_parsed_strictly(raw: str, expected: bool | None) -> None:
    values: dict[str, Any] = {}
    rest = RestClient("h", "u", "p", AsyncMock())
    rest._parse_auth_fields([{"fieldKey": "free-charging", "value": raw}], values)
    assert values["free_charging_enabled"] is expected


def test_active_errors_unknown_until_fetched() -> None:
    from custom_components.webasto_next_modbus.sensor import REST_SENSORS

    definition = next(d for d in REST_SENSORS if d.key == "active_errors")
    assert definition.value_fn(RestData()) is None
    assert definition.value_fn(RestData(active_errors=[])) == "ok"
    assert definition.value_fn(RestData(active_errors=["E1", "E2"])) == "E1, E2"


async def test_slow_rest_does_not_delay_modbus_setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, rest_entry: MockConfigEntry
) -> None:
    """Setup finishes and Modbus entities work while the web interface hangs."""

    never = asyncio.Event()

    async def _hang(method: str, url: Any, data: Any) -> Any:
        await never.wait()

    aioclient_mock.post(f"{BASE}/login", side_effect=_hang)
    rest_entry.add_to_hass(hass)
    async with asyncio.timeout(5):
        assert await hass.config_entries.async_setup(rest_entry.entry_id)
        await hass.async_block_till_done()

    assert rest_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.wallbox_charge_point_state").state == "available"
    assert hass.states.get("switch.wallbox_free_charging").state == STATE_UNAVAILABLE


async def test_invalid_error_list_keeps_previous_errors(
    client: RestClient, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE}/login", json={"access_token": "t"}, headers=JSON)
    aioclient_mock.get(f"{BASE}/sections/auth", json=[], headers=JSON)
    aioclient_mock.get(f"{BASE}/current-errors", json={"oops": True}, headers=JSON)

    data = await client.get_data(RestData(active_errors=["E7"]), include_system=False)

    assert data.active_errors == ["E7"]


async def test_login_without_token_is_not_an_auth_error(
    client: RestClient, aioclient_mock: AiohttpClientMocker
) -> None:
    from custom_components.webasto_next_modbus.rest_client import RestClientError

    aioclient_mock.post(f"{BASE}/login", json={"status": "starting"}, headers=JSON)

    with pytest.raises(RestClientError) as exc_info:
        await client.connect()
    assert not isinstance(exc_info.value, AuthenticationError)


async def test_concurrent_401s_share_one_failed_relogin(
    client: RestClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Every waiter gets the auth error; no extra rejected logins are sent."""

    logins = 0

    async def _login(method: str, url: Any, data: Any) -> Any:
        nonlocal logins
        logins += 1
        await asyncio.sleep(0.01)
        if logins == 1:
            return AiohttpClientMockResponse(method, url, json={"access_token": "t"}, headers=JSON)
        return AiohttpClientMockResponse(method, url, status=401)

    aioclient_mock.post(f"{BASE}/login", side_effect=_login)
    aioclient_mock.get(f"{BASE}/sections/auth", status=401)
    await client.connect()

    results = await asyncio.gather(
        *(client._get("/sections/auth") for _ in range(4)), return_exceptions=True
    )

    assert all(isinstance(result, AuthenticationError) for result in results)
    assert logins == 2
