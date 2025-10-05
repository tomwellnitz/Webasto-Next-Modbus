# Webasto Next Modbus Home Assistant Integration

This document captures architectural goals, the Modbus register model, and the high-level software design that powers the Webasto Next Modbus integration.

## Objectives

- Ship a resilient Home Assistant integration that surfaces telemetry and control surfaces for Webasto Next / Ampure Unite wallboxes via Modbus TCP.
- Provide rich entities and helper services without requiring users to handcraft YAML automations.
- Concentrate Modbus knowledge in a single place so new registers and behaviours can be added with minimal risk.
- Keep the codebase maintainable by favouring typed helpers, clear boundaries, and comprehensive automated tests.

## Functional requirements

- **Configuration flow** – Guided setup that collects host, port, unit ID, scan interval, and hardware variant while validating connectivity inline.
- **Modbus communication** – Async TCP client (pymodbus) with request batching, retry/backoff, and deterministic reconnect behaviour.
- **Entities** – Sensors for live telemetry and metadata, numbers for writable settings, and buttons for manual keep-alive and session control.
- **Services** – Dedicated helpers (`set_current`, `set_failsafe`, `send_keepalive`, `start_session`, `stop_session`) to complement the entity model.
- **Extensibility** – Centralised register descriptions drive entity creation so new datapoints require minimal boilerplate.
- **Testing** – Pytest suite with Modbus fixtures covering the config flow, coordinator, entities, services, and device triggers.
- **Documentation** – User-facing README plus architecture and development guides for maintainers.

## Domain model

- Integration domain: `webasto_next_modbus`.
- Device unique ID: `<host>-<unit_id>`.
- Units of measure: ampere (A), volt (V), watt (W), kilowatt-hour (kWh), second (s). Enumerations map integer states to human-readable labels.

## Register map

The register ranges are derived from community research and vendor documentation. Values are batched into segments of up to 110 registers to minimise Modbus overhead.

| Key | Address | Type | Scale | Description |
| --- | --- | --- | --- | --- |
| `serial_number` | 100 | string | – | Wallbox serial number |
| `charge_point_id` | 130 | string | – | Backend charge point identifier |
| `charge_point_brand` | 190 | string | – | Advertised brand name |
| `charge_point_model` | 210 | string | – | Model designation |
| `firmware_version` | 230 | string | – | Firmware version |
| `wallbox_date` | 290 | uint32 | – | Controller date (`YYYYMMDD`) |
| `wallbox_time` | 294 | uint32 | – | Controller time (`HHMMSS`) |
| `rated_power_w` | 400 | uint32 | – | Rated charging power |
| `phase_configuration` | 404 | uint16 | – | Phase configuration (`0 = single-phase`, `1 = three-phase`) |
| `charge_point_state` | 1000 | uint16 | – | IEC 61851 charge point state (`0–8`) |
| `charging_state` | 1001 | uint16 | – | Charging active (`0/1`) |
| `equipment_state` | 1002 | uint16 | – | EVSE equipment state |
| `cable_state` | 1004 | uint16 | – | Cable/vehicle state |
| `fault_code` | 1006 | uint16 | – | Vendor-specific error code |
| `current_l{1..3}` | 1008/1010/1012 | uint16 | ×0.001 | Phase currents |
| `voltage_l{1..3}` | 1014/1016/1018 | uint16 | – | Phase voltages |
| `active_power_total` | 1020 | uint32 | – | Total active power |
| `active_power_l{1..3}` | 1024/1028/1032 | uint32 | – | Per-phase active power |
| `energy_total` | 1036 | uint32 | ×0.001 | Lifetime energy counter |
| `ev_max_current` | 1108 | uint16 | – | Max allowable EV current |
| `charged_energy_wh` | 1502 | uint16 | – | Energy for the current session |
| `session_*` | 1504–1512 | uint32 | – | Session timestamps and durations |
| `failsafe_current` | 2000 | uint16 | – | Fail-safe current |
| `failsafe_timeout` | 2002 | uint16 | – | Fail-safe timeout |
| `charge_power_w` | 5000 | uint32 | – | Live charging power (holding register) |
| `set_current` | 5004 | uint16 | – | Writable dynamic current limit |
| `session_command` | 5006 | uint16 | – | Start/stop command register |
| `alive` | 6000 | uint16 | – | Keep-alive toggle |

## Software components

- `__init__.py` – Integration setup/teardown, service registration, and coordinator bootstrap.
- `const.py` – Constants, version metadata, register descriptions, and enum mappings.
- `hub.py` – `ModbusBridge` abstraction that wraps the async client, handles reconnect logic, and exposes read/write helpers.
- `coordinator.py` – `DataUpdateCoordinator` implementation that schedules read cycles and normalises raw register values.
- `config_flow.py` – User and options flows with validation and duplicate protection.
- Platform modules (`sensor.py`, `number.py`, `button.py`) – Entity classes backed by static descriptions.
- `services.yaml` – Service schemas surfaced to Home Assistant.

## Data flow

1. The config flow collects user input, performs a probe read, and stores a unique ID.
2. `async_setup_entry` creates the `ModbusBridge` and `DataUpdateCoordinator`.
3. The coordinator batches register reads, decodes values via helpers in `const.py`, and caches structured dictionaries.
4. Entities subscribe to the coordinator and expose the relevant keys to Home Assistant.
5. Write operations (`set_current`, `set_failsafe`, start/stop commands) call `ModbusBridge.async_write_register`, clamp inputs, and request an immediate refresh.
6. The keep-alive button/service toggles register `6000` and triggers an on-demand refresh to keep dashboards responsive.

## Error handling

- Communication errors raise `UpdateFailed`, automatically retried by the coordinator on the next polling interval.
- Individual register errors are logged and surfaced as `None` without blocking the entire payload.
- Write helpers clamp values to safe ranges and surface validation errors back to the UI.
- Persistent connectivity failures publish Home Assistant notifications to alert the user.

## Testing strategy

- Config flow tests covering happy path, connection failures, and duplicate detection.
- Coordinator tests that validate decoding, delta handling, and retry behaviour under simulated Modbus failures.
- Entity snapshot tests to guard the number of exposed entities and their metadata.
- Service tests asserting register writes, clamping, and refresh behaviour using the virtual wallbox simulator.
- `pytest-homeassistant-custom-component` fixtures provide a realistic Home Assistant core for integration-level tests.

## Assumptions and open items

- Defaults assume TCP port `502` and unit ID `255`; both are user-configurable during onboarding.
- Firmware revisions prior to `3.1` may omit the keep-alive register; the integration degrades gracefully by hiding the button.
- Session timestamp registers are kept as integers; template sensors can convert them to datetime values if required.
- Future enhancements include richer diagnostics, Energy Dashboard metadata, and additional translations.
