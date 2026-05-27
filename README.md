# Webasto Next / Unite for Home Assistant

Monitor and control Webasto Next and Ampure / Webasto Unite wallboxes in Home Assistant over Modbus TCP, with an optional REST API connection for extras such as LED control and firmware diagnostics.

[![Release](https://img.shields.io/github/v/release/tomwellnitz/Webasto-Next-Modbus?display_name=release)](https://github.com/tomwellnitz/Webasto-Next-Modbus/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/tomwellnitz/Webasto-Next-Modbus/ci.yaml?branch=main)](https://github.com/tomwellnitz/Webasto-Next-Modbus/actions/workflows/ci.yaml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange)](https://hacs.xyz)
[![License](https://img.shields.io/github/license/tomwellnitz/Webasto-Next-Modbus.svg)](LICENSE)
[![Maintenance](https://img.shields.io/maintenance/yes/2026.svg)](https://github.com/tomwellnitz/Webasto-Next-Modbus/commits/main)

> This is a community-maintained integration. It is not affiliated with, endorsed by, or supported by Webasto, Ampure, or the Home Assistant project.

## Supported hardware

- **Webasto Next** — fully supported in the current release.
- **Ampure / Webasto Unite** — fully supported since v1.2.0. The Unite uses a different register layout (telemetry on input registers, a few rescaled/widened registers, plus a three-phase switch); pick **Webasto / Ampure Unite** in the model selector during setup. Confirmed on firmware 3.156 and 3.187 ([#37](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues/37)).

The wallbox must be reachable over Modbus TCP (default port `502`). The REST API features additionally need the wallbox web-interface credentials.

## Features

- Local polling over Modbus TCP through an async update coordinator.
- Sensors for charge point and charging state, currents, power, energy, session data, fault codes and EV limits.
- Controls: dynamic charging current, fail-safe current and timeout, and start/stop/keep-alive buttons.
- A **Connected** binary sensor that reports reachability even while the wallbox is offline (useful in automations).
- Services for current limit, fail-safe, charging sessions and keep-alive frames.
- Optional REST API integration: LED brightness, free-charging toggle and tag ID, firmware/diagnostics sensors and a restart button.
- Device triggers (charging started/stopped, connection lost/restored, keep-alive sent) and ready-to-use blueprints.
- Automatic "Life Bit" keep-alive handling and resilient reconnect with back-off, so a power-cycled or still-booting wallbox recovers on its own.
- Tested against a virtual wallbox simulator.

## Requirements

- **Home Assistant** 2026.5.1 or newer (requires Python 3.14.2). On older Home Assistant, stay on release `1.1.5`.
- A supported wallbox (see [Supported hardware](#supported-hardware)) reachable over Modbus TCP.

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=tomwellnitz&repository=Webasto-Next-Modbus&category=integration)

Or add it manually:

1. In HACS, open the three-dot menu and choose **Custom repositories**.
2. Add `https://github.com/tomwellnitz/Webasto-Next-Modbus` with category **Integration**.
3. Install **Webasto Next** and restart Home Assistant.

To test upcoming changes, enable **Show beta versions** on the integration in HACS.

### Manual

1. Copy `custom_components/webasto_next_modbus/` from this repository into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

### Before you start: enable Modbus on the wallbox

Modbus TCP is **disabled by default** on the Webasto Next / Unite. Enable it first in the wallbox web interface: switch to the **expert/installer view**, then turn on **Modbus TCP** (default port `502`). Without this the integration cannot connect ([#36](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues/36)).

1. Go to **Settings → Devices & Services → Add Integration** and search for **Webasto Next**.
2. Enter your wallbox details:
   - **Host** — IP address or hostname (e.g. `192.168.1.50`).
   - **Port** — default `502`.
   - **Unit ID** — default `255`.
   - **Variant** — your hardware power rating (11 kW or 22 kW).

> The wallboxes do not advertise themselves on the network, so they are added manually by IP address; there is no auto-discovery.

### Optional: REST API

The REST API exposes features that are not available over Modbus (LED control, free charging, firmware info, diagnostics, restart).

1. Open the integration entry → three-dot menu → **Configure**.
2. Enable **REST API features** and enter the wallbox web-interface credentials (username default `admin`).

Credentials are stored in the Home Assistant config entry and redacted from downloaded diagnostics. If the wallbox later rejects them, a repair issue is raised so you can update the password; the Modbus side keeps working regardless.

## Entities

### Modbus (always available)

| Platform | Entities |
| :--- | :--- |
| Sensors | Charge point state, charging state, EVSE state, cable state, fault code, per-phase current and power, total energy, session energy and times, EV current limits, smart-vehicle detection. |
| Numbers | Charging current limit (0–32 A), fail-safe current (6–32 A), fail-safe timeout (6–120 s). |
| Buttons | Start charging, Stop charging, Send keep-alive. |
| Binary sensors | Connected (`device_class: connectivity`). |

### REST API (when enabled)

| Platform | Entities |
| :--- | :--- |
| Sensors | Comboard/Powerboard firmware (SW & HW), plug cycles, error counter, signal voltages L1/L2/L3, active errors. |
| Numbers | LED brightness (0–100 %). |
| Switches | Free charging. |
| Text | Free charging tag ID. |
| Buttons | Restart wallbox. |

## Services

All services live under the `webasto_next_modbus` domain.

| Service | Description |
| :--- | :--- |
| `set_current` | Set the dynamic charging current (0–32 A). |
| `set_failsafe` | Set the fail-safe current (6–32 A) and optional timeout (6–120 s). |
| `start_session` | Start a charging session. |
| `stop_session` | Stop the active charging session. |
| `send_keepalive` | Send a keep-alive frame manually. |

REST API services (when enabled):

| Service | Description |
| :--- | :--- |
| `set_led_brightness` | Set the LED brightness (0–100 %). |
| `set_free_charging` | Enable or disable free charging. |
| `restart_wallbox` | Restart the wallbox. |

> The "Life Bit" keep-alive is handled automatically in the background to keep the wallbox out of fail-safe mode; `send_keepalive` is only needed for manual control.

## Automations and blueprints

Ready-to-import blueprints live under **Settings → Automations & Scenes → Blueprints**:

- **FastCharge / FullCharge control** — start or stop charging from `input_boolean` toggles.
- **Charge target (kWh)** — charge a set amount of energy, then stop.
- **Charge until full** — stop automatically once charging power drops below a threshold.
- **Solar surplus optimizer** — adjust the charging current to grid export to maximise self-consumption.

Device triggers for charging start/stop and connection state are available for your own automations.

## Troubleshooting

- **Cannot connect** — verify host, port (`502`) and unit ID (`255`), and that the wallbox is reachable. Make sure **Modbus TCP is enabled on the wallbox** (expert view) — it is off by default. These wallboxes also accept only one Modbus TCP connection at a time, so make sure no other client (e.g. EVCC) holds it.
- **Values stuck or stale** — check the logs; transient errors are retried automatically, and a booting wallbox recovers on its own within a few minutes.
- **Diagnostics** — integration entry → three-dot menu → **Download diagnostics** (secrets are redacted).

See [`docs/support.md`](docs/support.md) for more.

## Development

```bash
uv sync            # install dependencies
uv run pytest      # run the test suite
uv run ruff check . # lint
```

A virtual wallbox simulator lets you develop without hardware. See [`docs/development.md`](docs/development.md) and [`docs/architecture.md`](docs/architecture.md).

## License and credits

Released under the [MIT License](LICENSE). Thanks to [@cdrfun](https://github.com/cdrfun) for the advanced-blueprint inspiration, and to the contributors on [#37](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues/37) for the Unite register readouts.
