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

*Note: Voltage sensors and some other registers from the vendor PDF are not exposed as they returned invalid data in testing.*

## Software components

- `__init__.py` – Integration setup/teardown, service registration, and coordinator bootstrap. Handles connection retries and starts the Life Bit loop.
- `const.py` – Constants, version metadata, register descriptions, and enum mappings.
- `hub.py` – `ModbusBridge` abstraction that wraps the async client, handles reconnect logic, exposes read/write helpers, and manages the background "Life Bit" loop.
- `coordinator.py` – `DataUpdateCoordinator` implementation that schedules read cycles and normalises raw register values.
- `config_flow.py` – User and options flows with validation and duplicate protection.
- Platform modules (`sensor.py`, `number.py`, `button.py`) – Entity classes backed by static descriptions.
- `services.yaml` – Service schemas surfaced to Home Assistant.

## Data flow

1. The config flow collects user input, performs a probe read, and stores a unique ID.
1. `async_setup_entry` creates the `ModbusBridge` and `DataUpdateCoordinator`.
1. After the coordinator completes its first refresh, the `ModbusBridge` starts a background "Life Bit" task.
1. The Life Bit task writes `1` to register `6000`, then polls every second until the wallbox clears it to `0`, then repeats. This prevents failsafe mode.
1. The coordinator batches register reads, decodes values via helpers in `const.py`, and caches structured dictionaries.
1. Entities subscribe to the coordinator and expose the relevant keys to Home Assistant.
1. Write operations (`set_current`, `set_failsafe`) call `ModbusBridge.async_write_register`, clamp inputs, and request an immediate refresh.
1. All operations share a single TCP connection protected by an asyncio lock.

## Error handling

- **Connection Retries**: During setup, the integration attempts to connect 3 times with a delay, notifying the user if it fails.
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
- Firmware revisions prior to `3.1` may omit the keep-alive register; the integration degrades gracefully by hiding the button.
- Session timestamp registers are kept as integers; template sensors can convert them to datetime values if required.
- Future enhancements include richer diagnostics, Energy Dashboard metadata, and additional translations.
