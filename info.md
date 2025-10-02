# Webasto Next Modbus

Integrate Webasto Next / Ampure Unite wallboxes with Home Assistant over Modbus TCP.

## Highlights

- Guided config flow with on-the-fly connection validation.
- DataUpdateCoordinator-backed polling for reliable register refreshes.
- Rich entity set: live telemetry sensors, writable number entities, and a keep-alive button.
- Dedicated services (`set_current`, `set_failsafe`, `send_keepalive`) for advanced automations.
- Thorough pytest suite covering config flows, entities, and service handlers.

## Requirements

- Home Assistant 2024.6.0 or newer.
- Wallbox reachable via Modbus TCP (default port 502).

## Useful links

- [Documentation](https://github.com/tomwellnitz/Webasto-Next-Modbus)
- [Issue tracker](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues)

Before releasing, replace the placeholder GitHub URLs with the actual repository location.
