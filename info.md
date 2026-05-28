# Webasto Next / Unite

Bring Webasto Next and Ampure / Webasto Unite wallboxes into Home Assistant via Modbus TCP and an optional REST API.

## Highlights

- Guided onboarding with immediate Modbus validation; model selector (Webasto Next or Webasto / Ampure Unite) and 11 kW (16 A) / 22 kW (32 A) variants.
- Reconfigure flow for in-place host/port/unit ID changes and a guided reauth flow when REST credentials are rejected.
- Rich entities: sensors, numbers, switches, buttons, text, and **Connected** + **Charging** binary sensors.
- Device triggers (charging, connection, cable, fault) and ready-to-import blueprints (FastCharge, Charge target, Charge until full, Solar surplus, Event notifications).
- Resilient polling: retry/backoff, automatic Life Bit keep-alive, optional REST diagnostics, redacted diagnostics download.
- HA quality scale **Platinum**: strict typing, shared aiohttp session, icon and exception translations, action-setup, full pytest suite.

## Requirements

- Home Assistant 2026.5.1 or newer (older HA users should stay on `1.1.5`).
- Wallbox reachable via Modbus TCP (default port `502`). Modbus must be enabled in the wallbox web interface (expert view) — it is off by default.

## Useful links

- [Repository & documentation](https://github.com/tomwellnitz/Webasto-Next-Modbus)
- [Issue tracker](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues)
