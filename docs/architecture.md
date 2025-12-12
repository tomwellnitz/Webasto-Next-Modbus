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
| `charge_point_id` | 1000 | uint32 | – | Charge Point ID |
| `serial_number` | 1002 | uint32 | – | Serial Number |
| `product_type` | 1004 | uint32 | – | Product Type |
| `firmware_version` | 1006 | uint16 | – | Firmware Version |
| `modbus_table_version` | 1008 | uint16 | – | Modbus Table Version |
| `grid_phase_config` | 1010 | uint16 | – | Grid Phase Configuration |
| `max_station_current` | 1012 | uint16 | – | Max Station Current |
| `evse_state` | 1100 | uint16 | – | IEC 61851 State (A-F) |
| `cable_state` | 1102 | uint16 | – | Cable State |
| `error_code` | 1104 | uint16 | – | Error Code |
| `charging_state` | 1106 | uint16 | – | Charging State |
| `current_l{1..3}` | 1108/1110/1112 | uint16 | – | Phase Currents (A) |
| `active_power_total` | 1114 | uint32 | – | Active Power Total (W) |
| `meter_reading_session` | 1116 | uint32 | – | Meter Reading Session (Wh) |
| `meter_reading_total` | 1118 | uint32 | – | Meter Reading Total (Wh) |
| `safe_current` | 1500 | uint16 | – | Safe Current (A) |
| `connection_timeout` | 1502 | uint16 | – | Connection Timeout (s) |
| `vehicle_max_current` | 1618 | uint16 | – | Vehicle Max Current (A) |
| `smart_vehicle_detected` | 1620 | uint32 | – | Smart Vehicle Detected |
| `charge_current_limit` | 2000 | uint16 | – | Charge Current Limit (A) |
| `charge_mode` | 2002 | uint16 | – | Charge Mode |
| `life_bit` | 6000 | uint16 | – | Life Bit (Keep-alive) |

*Note: Voltage sensors (1014-1018) and Charge Power (5000) were removed as they are not supported or write-only.*

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
2. `async_setup_entry` creates the `ModbusBridge` and `DataUpdateCoordinator`.
3. The `ModbusBridge` starts a background task that writes `1` to register `6000` and polls it until it becomes `0` (Life Bit handshake).
4. The coordinator batches register reads, decodes values via helpers in `const.py`, and caches structured dictionaries.
5. Entities subscribe to the coordinator and expose the relevant keys to Home Assistant.
6. Write operations (`set_current`, `set_failsafe`) call `ModbusBridge.async_write_register`, clamp inputs, and request an immediate refresh.

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
