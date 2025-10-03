<p align="center">
  <img src="logo.png" alt="Webasto Next Modbus" width="240" />
</p>

# Webasto Next Modbus

Integrate Webasto Next / Ampure Unite wallboxes with Home Assistant over Modbus TCP.

## Highlights

- Guided config flow with on-the-fly connection validation.
- Hardware profile selector for 11 kW (16 A) or 22 kW (32 A) wallboxes.
- DataUpdateCoordinator-backed polling for reliable register refreshes.
- Automatic retry/backoff with diagnostics export and persistent notifications on connection loss.
- Rich entity set: live telemetry sensors, writable number entities, and a keep-alive button.
- Dedicated services (`set_current`, `set_failsafe`, `send_keepalive`) for advanced automations.
- Thorough pytest suite covering config flows, entities, and service handlers.

## Requirements

- Home Assistant 2024.12 or newer.
- Wallbox reachable via Modbus TCP (default port 502).

## Useful links

- [Documentation](https://github.com/tomwellnitz/Webasto-Next-Modbus)
- [Issue tracker](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues)
