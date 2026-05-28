# Webasto Next Home Assistant Integration

This document captures architectural goals, the communication protocols (Modbus TCP and REST API), and the high-level software design that powers the Webasto Next integration.

## Objectives

- Ship a resilient Home Assistant integration that surfaces telemetry and control surfaces for Webasto Next / Ampure Unite wallboxes via Modbus TCP.
- Provide rich entities and helper services without requiring users to handcraft YAML automations.
- Concentrate Modbus knowledge in a single place so new registers and behaviours can be added with minimal risk.
- Keep the codebase maintainable by favouring typed helpers, clear boundaries, and comprehensive automated tests.

## Functional requirements

- **Configuration flow** – Guided setup that collects host, port, unit ID, model (Next vs Unite), variant, and scan interval, validating connectivity inline. Optional REST API credentials.
- **Reconfigure & reauth flows** – `async_step_reconfigure` allows changing host, port, unit ID and entry name in place (no remove-and-readd). `async_step_reauth` is started automatically when the wallbox rejects REST credentials (HTTP 401) to walk the user through entering new ones; the Modbus side keeps working throughout.
- **Modbus communication** – Async TCP client (pymodbus) with request batching, retry/backoff, and deterministic reconnect behaviour. Modbus exception responses are distinguished from transport errors: an unsupported optional block is auto-detected and dropped from the read plan, while a required block raises a typed `WebastoModbusDeviceError`.
- **REST API communication** – Optional async HTTPS client (aiohttp) sharing Home Assistant's `async_get_clientsession`, with JWT authentication, auto token refresh, retry-with-backoff for transient errors, and graceful degradation.
- **Entities** – Sensors for live telemetry and metadata; numbers for writable settings; switches for free-charging and (Unite only) three-phase mode; buttons for manual keep-alive, session control, and (REST) restart; text for the free-charging tag ID; binary sensors for **Connected** (always-available connectivity) and **Charging** (`battery_charging` device class).
- **Services** – Dedicated helpers (`set_current`, `set_failsafe`, `send_keepalive`, `start_session`, `stop_session`) for Modbus, plus REST API services (`set_led_brightness`, `set_free_charging`, `restart_wallbox`). Registered in `async_setup` so they exist before any config entry is set up.
- **Device triggers** – `charging_started`, `charging_stopped`, `connection_lost`, `connection_restored`, `keepalive_sent`, `cable_connected`, `cable_disconnected`, `fault_occurred` (with English / German translations), used by the bundled blueprints and available for user automations.
- **Diagnostics** – Downloadable config-entry diagnostics with REST credentials redacted.
- **Quality scale** – Platinum: strict typing (`mypy --strict` + `py.typed`), `inject-websession` (HA shared aiohttp session), async-dependency, icon translations (`icons.json`), exception translations, action-setup, `PARALLEL_UPDATES` declared on every platform.
- **Extensibility** – Centralised register descriptions drive entity creation so new datapoints require minimal boilerplate.
- **Testing** – Pytest suite with virtual-wallbox fixtures covering the config flow (incl. reconfigure and reauth), coordinator, entities, services, and device triggers; `pytest-homeassistant-custom-component` provides a realistic Home Assistant core.
- **Documentation** – User-facing README and support/troubleshooting page, plus architecture and development guides for maintainers.

## Domain model

- Integration domain: `webasto_next_modbus`.
- Device unique ID: `<host>-<unit_id>`.
- Units of measure: ampere (A), volt (V), watt (W), kilowatt-hour (kWh), second (s). Enumerations map integer states to human-readable labels.

## Register map

The register ranges are derived from community research and vendor documentation. Values are batched into segments of up to 110 registers to minimise Modbus overhead.

### Sensor Registers (Read-Only)

| Key | Address | Type | Description |
| --- | --- | --- | --- |
| `charge_point_state` | 1000 | uint16 | Charge Point State (enum) |
| `charging_state` | 1001 | uint16 | Charging State (idle/charging) |
| `equipment_state` | 1002 | uint16 | EVSE State (starting/running/fault/disabled) |
| `cable_state` | 1004 | uint16 | Cable State |
| `fault_code` | 1006 | uint16 | EVSE Fault Code |
| `current_l1_a` | 1008 | uint16 | Phase 1 Current (mA scale) |
| `current_l2_a` | 1010 | uint16 | Phase 2 Current (mA scale) |
| `current_l3_a` | 1012 | uint16 | Phase 3 Current (mA scale) |
| `active_power_total_w` | 1020 | uint32 | Total Active Power (W) |
| `active_power_l{1,2,3}_w` | 1024/1028/1032 | uint32 | Per-Phase Power (W) |
| `energy_total_kwh` | 1036 | uint32 | Total Energy (Wh scale) |
| `session_max_current_a` | 1100 | uint16 | Session Max Current (A) |
| `evse_min/max_current_a` | 1102/1104 | uint16 | EVSE Current Limits (A) |
| `cable_max_current_a` | 1106 | uint16 | Cable Max Current (A) |
| `ev_max_current_a` | 1108 | uint16 | EV Reported Max Current (A) |
| `charged_energy_wh` | 1502 | uint16 | Session Charged Energy (Wh) |
| `session_start_time` | 1504 | uint32 | Session Start Time (hhmmss) |
| `session_duration_s` | 1508 | uint32 | Session Duration (s) |
| `session_end_time` | 1512 | uint32 | Session End Time (hhmmss) |
| `session_user_id` | 1600 | string | User ID (20 chars) |
| `smart_vehicle_detected` | 1620 | uint32 | Smart Vehicle Detection |

### Number Registers (Read/Write)

| Key | Address | Type | Range | Description |
| --- | --- | --- | --- | --- |
| `failsafe_current_a` | 2000 | uint16 | 6–32 A | Fallback current when EMS offline |
| `failsafe_timeout_s` | 2002 | uint16 | 6–120 s | Time before failsafe activates |
| `set_current_a` | 5004 | uint16 | 0–32 A | Dynamic charging current limit (write-only) |

### Button/Control Registers (Write-Only)

| Key | Address | Value | Description |
| --- | --- | --- | --- |
| `send_keepalive` | 6000 | 1 | Life Bit – must be written regularly |
| `start_session` | 5006 | 1 | Start charging session |
| `stop_session` | 5006 | 2 | Stop charging session |

*Note: Voltage sensors and some other registers from the vendor PDF are not exposed on the Next as they returned invalid data in testing.*

### Webasto / Ampure Unite differences (v1.2.0+)

Picking the **Unite** model in the config flow switches to a corrected register map (community readouts from issue [#37](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues/37), confirmed on firmware 3.156 and 3.187):

- The telemetry block (~100–1513) is read as **input registers** on the Unite; the Next answers on both holding and input, the Unite only on input. This is why a Unite configured as "Next" reads all sensors as `0`.
- `energy_total_kwh` is decoded as a 32-bit value across registers `1036`+`1037` in **0.1 kWh** units.
- `charged_energy_wh` (`1502`) is a `uint32` on the Unite.
- `charge_point_state` (`1000`) uses the Unite's 9-state enum.
- Next-only registers (session user id `1600`, smart-vehicle-detected `1620`, start/stop-session command `5006`) are not read on the Unite.
- Unite-only optional registers: per-phase voltage `1014`/`1016`/`1018` (volts), chargepoint power `400`, installed phase count `404`, and the active phase mode at `405` — written by the "Three-phase charging" switch (`0` = single-phase, `1` = three-phase) and read back from the same register. Register `405` is undocumented in the vendor spec; phase switching has been confirmed on firmware 3.187 (#37) and the switch carries `_attr_assumed_state = True` because behaviour on other Unite firmwares is unverified.

## Software components

- `__init__.py` – Integration setup/teardown, service registration in `async_setup` (action-setup rule), and coordinator bootstrap. Handles connection retries and starts the Life Bit loop.
- `const.py` – Constants, register descriptions (including the Unite-specific layout), and enum mappings. The integration version lives in `manifest.json` / `pyproject.toml`, not here.
- `hub.py` – `ModbusBridge` abstraction that wraps the async client, handles reconnect logic, exposes read/write helpers, and manages the background "Life Bit" loop.
- `rest_client.py` – `RestClient` for optional REST API communication. Handles JWT authentication, token refresh, and API calls for features not available via Modbus; uses Home Assistant's shared aiohttp session.
- `coordinator.py` – `DataUpdateCoordinator` implementation that schedules read cycles, normalises raw register values, optionally fetches REST API data, and emits the dispatcher-based device triggers when relevant state changes are detected. On REST `401` it starts the reauth flow via `config_entry.async_start_reauth`.
- `config_flow.py` – User, options, **reconfigure** and **reauth** flows with validation and duplicate protection. Includes optional REST API credential configuration.
- `device_trigger.py` – Device-trigger registry and helpers used by `coordinator.py` to fire triggers (`async_fire_device_trigger`) for charging / connection / cable / fault events.
- `diagnostics.py` – Config-entry diagnostics download (REST username and password are redacted).
- Platform modules (`sensor.py`, `number.py`, `button.py`, `switch.py`, `binary_sensor.py`, `text.py`) – Entity classes backed by static descriptions. `binary_sensor.py` exposes the always-available **Connected** sensor and a **Charging** sensor (`device_class: battery_charging`); the `switch`/`text` platforms provide REST-backed entities (free-charging toggle and tag ID) plus the Unite-only three-phase switch.
- `services.yaml` – Service schemas surfaced to Home Assistant.
- `icons.json` – Entity icons (icon-translations rule).
- `quality_scale.yaml` – Per-rule status for the HA integration quality scale (Platinum).
- `translations/en.json`, `translations/de.json` – Entity, state, exception, device-trigger, config-flow and options-flow translations.

## Data flow

1. The config flow collects user input, performs a probe read, and stores a unique ID.
1. `async_setup_entry` creates the `ModbusBridge`, optionally the `WebastoRestClient`, and the `DataUpdateCoordinator`.
1. After the coordinator completes its first refresh, the `ModbusBridge` starts a background "Life Bit" task.
1. The Life Bit task writes `1` to register `6000`, then polls every second until the wallbox clears it to `0`, then repeats. This prevents failsafe mode.
1. The coordinator batches register reads, decodes values via helpers in `const.py`, and caches structured dictionaries.
1. If REST API is enabled, the coordinator also fetches data from the wallbox web interface (firmware info, LED brightness, diagnostics, etc.).
1. Entities subscribe to the coordinator and expose the relevant keys to Home Assistant.
1. Write operations (`set_current`, `set_failsafe`) call `ModbusBridge.async_write_register`, clamp inputs, and request an immediate refresh.
1. REST API write operations (LED brightness, free charging, restart) call `WebastoRestClient` methods.
1. All Modbus operations share a single TCP connection protected by an asyncio lock. REST operations use a separate aiohttp session.

## Error handling

- **Connection Retries**: During setup, the integration attempts to connect up to 5 times with a delay, notifying the user if it fails.
- **Communication errors**: Raise `UpdateFailed`, automatically retried by the coordinator on the next polling interval.
- **Individual register errors**: Logged and surfaced as `None` without blocking the entire payload.
- **Write helpers**: Clamp values to safe ranges and surface validation errors back to the UI.
- **Persistent connectivity failures**: Publish Home Assistant notifications to alert the user.

## Testing strategy

- Config flow tests covering happy path, connection failures, and duplicate detection.
- Coordinator tests that validate decoding, delta handling, and retry behaviour under simulated Modbus failures.
- Entity snapshot tests to guard the number of exposed entities and their metadata.
- Service tests asserting register writes, clamping, and refresh behaviour using the virtual wallbox simulator.
- `pytest-homeassistant-custom-component` fixtures provide a realistic Home Assistant core for integration-level tests.

## Assumptions and open items

- Defaults assume TCP port `502` and unit ID `255`; both are user-configurable during onboarding.
- The wallbox accepts a **single** Modbus TCP client at a time; the integration owns that slot for the lifetime of the config entry. A booting wallbox or a stale socket from another client therefore manifests as transient connection errors that are retried automatically.
- Registers a given firmware doesn't implement are handled automatically: optional blocks are dropped from the read plan after the first error response, and the corresponding entities become unavailable rather than spamming warnings.
- The Unite three-phase switch (holding register `405`) is undocumented in the vendor Modbus spec and confirmed on firmware 3.187 ([#37](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues/37)); on other Unite firmwares the behaviour is unverified.
- The wallbox web interface uses a self-signed TLS certificate, so the REST client is built on `async_get_clientsession(hass, verify_ssl=False)`.

## Future enhancements

- **Additional translations**: Expand language support beyond English and German (e.g., French, Spanish, Dutch).
- **Off-Peak Charging**: Leverage the REST API to control off-peak charging schedules and time windows.
- **Skip Random Delay**: Add button entity to skip the randomized charging delay via REST API.
- **Network diagnostics**: Surface additional network interface information from the REST API.
